package lab;

import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.LongSupplier;

/** Local synthetic inference service. No remote model, credentials or real payment data. */
public final class Gateway implements AutoCloseable {
    public interface Model { double predict(double[] features) throws Exception; }
    public static final class Rejected extends RuntimeException {
        public final int status;
        public Rejected(int status, String message) { super(message); this.status=status; }
    }
    public record Config(int queue, int records, long ttlMillis, int retries, int threshold, long cooldownMillis) {
        public Config {
            if(queue<1 || records<queue+1 || ttlMillis<1 || retries<0 || retries>3 || threshold<1 || cooldownMillis<1)
                throw new IllegalArgumentException("INVALID_CONFIG");
        }
    }
    public record Result(String id,String state,Double value,String error,boolean cacheHit) {
        public String json() {
            return "{\"id\":\""+id+"\",\"state\":\""+state+"\",\"value\":"+value+
                ",\"error\":"+(error==null?"null":"\""+error+"\"")+",\"cacheHit\":"+cacheHit+"}";
        }
    }
    private static final class Job {
        String id, key, fingerprint, state="QUEUED", error;
        Double value;
        boolean cached;
        long expires=Long.MAX_VALUE;
        Job(String id,String key,String fingerprint){this.id=id;this.key=key;this.fingerprint=fingerprint;}
        Result result(){return new Result(id,state,value,error,cached);}
    }
    private record Cached(double value,long expires){}
    private final Config config;
    private final Model model;
    private final LongSupplier time;
    private final ThreadPoolExecutor pool;
    private final Map<String,Job> jobs=new HashMap<>(), keys=new HashMap<>();
    private final Map<String,Cached> cache=new HashMap<>();
    private boolean closing, probe;
    private int failures;
    private long openUntil, accepted, rejected, attempts, hits, succeeded, failed;

    public Gateway(Config config,Model model,LongSupplier time){
        this.config=config;this.model=model;this.time=time;
        pool=new ThreadPoolExecutor(1,1,0,TimeUnit.MILLISECONDS,new ArrayBlockingQueue<>(config.queue()),
            Thread.ofPlatform().name("synthetic-model-",0).factory(),new ThreadPoolExecutor.AbortPolicy());
    }
    public static double synthetic(double[] features){
        double sum=0;for(double value:features)sum+=value;
        return 1.0/(1.0+Math.exp(-sum/features.length));
    }
    private static String fingerprint(double[] input){
        try {
            byte[] hash=MessageDigest.getInstance("SHA-256").digest(Arrays.toString(input).getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        }catch(Exception ex){throw new IllegalStateException(ex);}
    }
    public static double[] validate(double[] input){
        if(input==null || input.length<1 || input.length>16)throw new Rejected(400,"FEATURE_COUNT");
        double[] copy=input.clone();
        for(int i=0;i<copy.length;i++){
            if(!Double.isFinite(copy[i]) || Math.abs(copy[i])>100)throw new Rejected(400,"FEATURE_RANGE");
            if(copy[i]==0)copy[i]=0; // canonical signed zero
        }
        return copy;
    }
    private void prune(){
        long now=time.getAsLong();
        jobs.values().removeIf(j->{
            if(j.expires<=now){keys.remove(j.key,j);return true;}return false;
        });
        cache.values().removeIf(c->c.expires<=now);
    }
    public synchronized Result submit(String key,double[] input){
        if(closing)throw reject(503,"SHUTTING_DOWN");
        if(key==null || !key.matches("[A-Za-z0-9_-]{1,64}"))throw reject(400,"IDEMPOTENCY_KEY");
        double[] features=validate(input);
        String fp=fingerprint(features);
        prune();
        Job old=keys.get(key);
        if(old!=null){
            if(!old.fingerprint.equals(fp))throw reject(409,"IDEMPOTENCY_CONFLICT");
            return old.result();
        }
        if(jobs.size()>=config.records())throw reject(429,"RECORD_CAPACITY");
        Cached cached=cache.get(fp);
        Job job=new Job(UUID.randomUUID().toString(),key,fp);
        if(cached!=null){
            job.state="SUCCEEDED";job.value=cached.value;job.cached=true;
            job.expires=time.getAsLong()+config.ttlMillis();
            jobs.put(job.id,job);keys.put(key,job);hits++;accepted++;
            return job.result();
        }
        // Work admitted to the queue still checks the breaker before every model call.
        jobs.put(job.id,job);keys.put(key,job);
        try {pool.execute(()->execute(job,features));accepted++;return job.result();}
        catch(RejectedExecutionException ex){
            jobs.remove(job.id);keys.remove(key);throw reject(429,"QUEUE_FULL");
        }
    }
    private Rejected reject(int status,String reason){rejected++;return new Rejected(status,reason);}
    private synchronized boolean permit(){
        if(closing && Thread.currentThread().isInterrupted())return false;
        if(openUntil==0)return true;
        if(time.getAsLong()<openUntil || probe)return false;
        probe=true;return true;
    }
    private synchronized void modelSuccess(){failures=0;openUntil=0;probe=false;}
    private synchronized void modelFailure(){
        failures++;probe=false;
        if(failures>=config.threshold())openUntil=time.getAsLong()+config.cooldownMillis();
    }
    private void execute(Job job,double[] features){
        synchronized(this){if(!job.state.equals("QUEUED"))return;job.state="RUNNING";}
        String error="MODEL_FAILURE";
        for(int n=0;n<=config.retries();n++){
            if(Thread.currentThread().isInterrupted()){error="CANCELLED";break;}
            if(!permit()){error="CIRCUIT_OPEN";break;}
            try{
                synchronized(this){attempts++;}
                double value=model.predict(features.clone());
                if(!Double.isFinite(value))throw new IllegalStateException("NONFINITE_MODEL");
                modelSuccess();
                synchronized(this){
                    if(job.state.equals("CANCELLED"))return;
                    job.state="SUCCEEDED";job.value=value;job.expires=time.getAsLong()+config.ttlMillis();
                    cache.put(job.fingerprint,new Cached(value,job.expires));succeeded++;
                }
                return;
            }catch(InterruptedException ex){Thread.currentThread().interrupt();error="CANCELLED";break;}
            catch(Exception ex){modelFailure();} // bounded immediate retries; never expose provider exception content
        }
        synchronized(this){
            if(job.state.equals("CANCELLED"))return;
            job.state=error.equals("CANCELLED")?"CANCELLED":"FAILED";job.error=error;
            job.expires=time.getAsLong()+config.ttlMillis();failed++;
        }
    }
    public synchronized Result get(String id){
        prune();Job job=jobs.get(id);
        if(job==null)throw reject(404,"JOB_NOT_FOUND");
        return job.result();
    }
    public synchronized String metrics(){
        prune();
        String circuit=openUntil==0?"CLOSED":time.getAsLong()<openUntil?"OPEN":"HALF_OPEN";
        return "{\"accepted\":"+accepted+",\"rejected\":"+rejected+",\"attempts\":"+attempts+
            ",\"succeeded\":"+succeeded+",\"failed\":"+failed+",\"cacheHits\":"+hits+
            ",\"queued\":"+pool.getQueue().size()+",\"records\":"+jobs.size()+",\"cacheEntries\":"+cache.size()+
            ",\"circuit\":\""+circuit+"\",\"closing\":"+closing+"}";
    }
    public void shutdown(long waitMillis){
        synchronized(this){closing=true;}
        pool.shutdown();
        boolean done=false;
        try{done=pool.awaitTermination(waitMillis,TimeUnit.MILLISECONDS);}
        catch(InterruptedException ex){Thread.currentThread().interrupt();}
        if(!done){
            pool.shutdownNow();
            synchronized(this){
                for(Job job:jobs.values())if(job.state.equals("QUEUED")||job.state.equals("RUNNING")){
                    job.state="CANCELLED";job.error="CANCELLED";job.expires=time.getAsLong()+config.ttlMillis();failed++;
                }
            }
        }
    }
    @Override public void close(){shutdown(3000);}

    public HttpServer http(int port)throws IOException{
        HttpServer server=HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(),port),16);
        server.createContext("/",exchange->{
            try{
                String host=exchange.getRequestHeaders().getFirst("Host");
                int actual=server.getAddress().getPort();
                if(!Objects.equals(host,"localhost:"+actual)&&!Objects.equals(host,"127.0.0.1:"+actual))
                    throw new Rejected(403,"HOST");
                String path=exchange.getRequestURI().getPath();
                if(exchange.getRequestURI().getRawQuery()!=null)throw new Rejected(400,"QUERY_NOT_SUPPORTED");
                String method=exchange.getRequestMethod();
                if(method.equals("GET")&&path.equals("/health"))respond(exchange,200,"{\"service\":\"local-synthetic-inference\",\"model\":\"deterministic-v1\"}");
                else if(method.equals("GET")&&path.equals("/metrics"))respond(exchange,200,metrics());
                else if(method.equals("GET")&&path.matches("/jobs/[a-f0-9-]{36}"))respond(exchange,200,get(path.substring(6)).json());
                else if(method.equals("POST")&&path.equals("/infer")){
                    if(!"application/x-www-form-urlencoded".equals(exchange.getRequestHeaders().getFirst("Content-Type")))
                        throw new Rejected(415,"CONTENT_TYPE");
                    byte[] bytes=exchange.getRequestBody().readNBytes(1025);
                    if(bytes.length>1024)throw new Rejected(413,"BODY_LIMIT");
                    String body=new String(bytes,StandardCharsets.UTF_8);
                    if(!body.startsWith("features=")||body.contains("&"))throw new Rejected(400,"FIELDS");
                    String[] parts=URLDecoder.decode(body.substring(9),StandardCharsets.UTF_8).split(",",-1);
                    if(parts.length>16)throw new Rejected(400,"FEATURE_COUNT");
                    double[] f=new double[parts.length];
                    try{for(int i=0;i<parts.length;i++)f[i]=Double.parseDouble(parts[i]);}
                    catch(NumberFormatException ex){throw new Rejected(400,"FEATURE_NUMBER");}
                    Result result=submit(exchange.getRequestHeaders().getFirst("Idempotency-Key"),f);
                    respond(exchange,result.state().equals("SUCCEEDED")?200:202,result.json());
                }else throw new Rejected(method.equals("GET")?404:405,"ROUTE_OR_METHOD");
            }catch(Rejected ex){respond(exchange,ex.status,"{\"error\":\""+ex.getMessage()+"\"}");}
            catch(IllegalArgumentException ex){respond(exchange,400,"{\"error\":\"INVALID_ENCODING\"}");}
            catch(Exception ex){respond(exchange,500,"{\"error\":\"INTERNAL\"}");}
            finally{exchange.close();}
        });
        // HTTP parsing remains serialized; model execution is asynchronous and queue-bounded.
        server.start();return server;
    }
    private static void respond(HttpExchange exchange,int status,String body)throws IOException{
        byte[] bytes=body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type","application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control","no-store");
        exchange.getResponseHeaders().set("X-Content-Type-Options","nosniff");
        exchange.sendResponseHeaders(status,bytes.length);
        exchange.getResponseBody().write(bytes);
    }
    public static void main(String[] args)throws Exception{
        int port=args.length==0?4193:Integer.parseInt(args[0]);
        Gateway gateway=new Gateway(new Config(8,128,60_000,1,3,5_000),Gateway::synthetic,System::currentTimeMillis);
        HttpServer server=gateway.http(port);
        Runtime.getRuntime().addShutdownHook(new Thread(()->{server.stop(1);gateway.close();}));
        System.out.println("Local synthetic gateway on http://localhost:"+server.getAddress().getPort());
    }
}
