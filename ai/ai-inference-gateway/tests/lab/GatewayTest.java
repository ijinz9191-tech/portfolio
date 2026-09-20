package lab;
import java.net.*;
import java.net.http.*;
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import com.sun.net.httpserver.HttpServer;

public final class GatewayTest {
    static int count;
    static void check(boolean ok,String reason){if(!ok)throw new AssertionError(reason);}
    interface Test {void run()throws Exception;}
    static void test(String name,Test body)throws Exception{body.run();count++;System.out.println("PASS "+name);}
    static Gateway.Config cfg(){return new Gateway.Config(2,8,100,1,3,50);}
    static Gateway.Result done(Gateway g,String id)throws Exception{
        for(int i=0;i<400;i++){var r=g.get(id);if(!r.state().equals("QUEUED")&&!r.state().equals("RUNNING"))return r;Thread.sleep(5);}
        throw new AssertionError("completion timeout");
    }
    static void rejects(int code,Runnable body){
        try{body.run();throw new AssertionError("expected rejection "+code);}
        catch(Gateway.Rejected ex){check(ex.status==code,"wrong rejection "+ex.status);}
    }
    public static void main(String[] args)throws Exception{
        test("deterministic prediction and finite validation",()->{
            check(Gateway.synthetic(new double[]{0,0})==0.5,"score");
            for(double[] bad:new double[][]{new double[0],new double[17],{Double.NaN},{Double.POSITIVE_INFINITY},{101}})
                rejects(400,()->Gateway.validate(bad));
        });
        test("idempotency replay conflict and immutable feature copy",()->{
            AtomicLong now=new AtomicLong(1000);
            try(var g=new Gateway(cfg(),Gateway::synthetic,now::get)){
                double[] input={0};var first=g.submit("same",input);input[0]=50;
                check(done(g,first.id()).value()==0.5,"copied input");
                check(g.submit("same",new double[]{0}).id().equals(first.id()),"replay id");
                rejects(409,()->g.submit("same",new double[]{1}));
                rejects(400,()->g.submit("bad key",new double[]{0}));
            }
        });
        test("TTL cache expiry and record eviction",()->{
            AtomicLong now=new AtomicLong(1000);AtomicInteger calls=new AtomicInteger();
            try(var g=new Gateway(cfg(),f->{calls.incrementAndGet();return 0.25;},now::get)){
                var first=g.submit("a",new double[]{1});done(g,first.id());
                check(g.submit("b",new double[]{1}).cacheHit(),"cache");
                check(calls.get()==1,"not recomputed");
                now.addAndGet(101);rejects(404,()->g.get(first.id()));
                done(g,g.submit("a",new double[]{1}).id());check(calls.get()==2,"expired recomputed");
            }
        });
        test("bounded queue saturation removes rejected idempotency reservation",()->{
            CountDownLatch entered=new CountDownLatch(1),release=new CountDownLatch(1);
            try(var g=new Gateway(new Gateway.Config(1,8,1000,0,3,50),f->{entered.countDown();release.await();return 1;},System::currentTimeMillis)){
                var a=g.submit("a",new double[]{1});check(entered.await(2,TimeUnit.SECONDS),"entered");
                var b=g.submit("b",new double[]{2});
                rejects(429,()->g.submit("c",new double[]{3}));
                release.countDown();done(g,a.id());done(g,b.id());
                check(done(g,g.submit("c",new double[]{3}).id()).state().equals("SUCCEEDED"),"retry after overload");
            }finally{release.countDown();}
        });
        test("bounded retries recover transient worker failure",()->{
            AtomicInteger calls=new AtomicInteger();
            try(var g=new Gateway(cfg(),f->{if(calls.getAndIncrement()==0)throw new Exception("private-provider-detail");return .7;},()->1000)){
                check(done(g,g.submit("retry",new double[]{1}).id()).value()==.7,"recovered");
                check(calls.get()==2,"bounded retry");
            }
        });
        test("circuit opens blocks calls and half-open probe recovers",()->{
            AtomicLong now=new AtomicLong(1000);AtomicBoolean broken=new AtomicBoolean(true);AtomicInteger calls=new AtomicInteger();
            try(var g=new Gateway(new Gateway.Config(2,8,1000,0,1,50),f->{calls.incrementAndGet();if(broken.get())throw new Exception("private");return .9;},now::get)){
                check(done(g,g.submit("a",new double[]{1}).id()).state().equals("FAILED"),"failure");
                check(done(g,g.submit("b",new double[]{2}).id()).error().equals("CIRCUIT_OPEN"),"open");
                check(calls.get()==1,"open prevented call");
                broken.set(false);now.addAndGet(51);
                check(done(g,g.submit("c",new double[]{3}).id()).value()==.9,"probe recovered");
                check(g.metrics().contains("\"circuit\":\"CLOSED\""),"closed");
            }
        });
        test("nonfinite model output cannot enter cache",()->{
            try(var g=new Gateway(cfg(),f->Double.NaN,()->1000)){
                var r=done(g,g.submit("a",new double[]{1}).id());
                check(r.state().equals("FAILED")&&r.value()==null,"nonfinite failed");
                check(g.metrics().contains("\"cacheEntries\":0"),"no invalid cache");
            }
        });
        test("record capacity cannot evict active idempotency",()->{
            CountDownLatch release=new CountDownLatch(1);
            try(var g=new Gateway(new Gateway.Config(1,2,1000,0,3,50),f->{release.await();return 1;},()->1000)){
                var a=g.submit("a",new double[]{1});
                Thread.sleep(20);g.submit("b",new double[]{2});
                rejects(429,()->g.submit("c",new double[]{3}));
                check(g.submit("a",new double[]{1}).id().equals(a.id()),"active replay");
                release.countDown();
            }finally{release.countDown();}
        });
        test("graceful shutdown drains work then denies admissions",()->{
            var g=new Gateway(cfg(),Gateway::synthetic,()->1000);
            var r=g.submit("a",new double[]{0});g.shutdown(2000);
            check(g.get(r.id()).state().equals("SUCCEEDED"),"drained");
            rejects(503,()->g.submit("b",new double[]{0}));
        });
        test("forced shutdown cancels running and queued jobs",()->{
            CountDownLatch entered=new CountDownLatch(1);
            var g=new Gateway(cfg(),f->{entered.countDown();Thread.sleep(10000);return 1;},()->1000);
            var a=g.submit("a",new double[]{1});check(entered.await(2,TimeUnit.SECONDS),"started");
            var b=g.submit("b",new double[]{2});g.shutdown(1);
            check(g.get(a.id()).state().equals("CANCELLED"),"running cancelled");
            check(g.get(b.id()).state().equals("CANCELLED"),"queued cancelled");
        });
        test("restart explicitly loses ephemeral state but serves new work",()->{
            String id;
            try(var g=new Gateway(cfg(),Gateway::synthetic,()->1000)){id=g.submit("a",new double[]{0}).id();done(g,id);}
            try(var g=new Gateway(cfg(),Gateway::synthetic,()->1000)){
                rejects(404,()->g.get(id));check(done(g,g.submit("a",new double[]{0}).id()).value()==.5,"fresh restart");
            }
        });
        test("actual HTTP inference polling metrics and invalid inputs",()->{
            try(var g=new Gateway(cfg(),Gateway::synthetic,()->1000)){
                HttpServer server=g.http(0);
                try{
                    var client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
                    String base="http://localhost:"+server.getAddress().getPort();
                    var request=HttpRequest.newBuilder(URI.create(base+"/infer")).header("Content-Type","application/x-www-form-urlencoded")
                        .header("Idempotency-Key","http-one").POST(HttpRequest.BodyPublishers.ofString("features=0,0")).build();
                    var response=client.send(request,HttpResponse.BodyHandlers.ofString());
                    check(response.statusCode()==202,"accepted");
                    String id=response.body().split("\"id\":\"")[1].split("\"")[0];done(g,id);
                    for(String path:new String[]{"/health","/metrics","/jobs/"+id}){
                        var result=client.send(HttpRequest.newBuilder(URI.create(base+path)).GET().build(),HttpResponse.BodyHandlers.ofString());
                        check(result.statusCode()==200,"GET "+path);
                    }
                    for(String body:new String[]{"features=NaN","features=0&secret=value","features=","features=%GG","features="+"1".repeat(1025)}){
                        var bad=HttpRequest.newBuilder(URI.create(base+"/infer")).header("Content-Type","application/x-www-form-urlencoded")
                            .header("Idempotency-Key","bad").POST(HttpRequest.BodyPublishers.ofString(body)).build();
                        int status=client.send(bad,HttpResponse.BodyHandlers.ofString()).statusCode();
                        check(status==400||status==413,"bad input rejected");
                    }
                }finally{server.stop(0);}
            }
        });
        System.out.println("RESULT "+count+" passed, 0 failed");
    }
}
