package lab.delivery;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

import static lab.delivery.DeliveryCommandLedger.Status;

public final class DeliveryCommandLedgerTest {
    private static final List<String> passed = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        run("create", DeliveryCommandLedgerTest::create);
        run("idempotent create retry", DeliveryCommandLedgerTest::idempotentCreate);
        run("command payload conflict", DeliveryCommandLedgerTest::commandConflict);
        run("duplicate order", DeliveryCommandLedgerTest::duplicateOrder);
        run("assign", DeliveryCommandLedgerTest::assign);
        run("courier capacity", DeliveryCommandLedgerTest::capacity);
        run("optimistic version", DeliveryCommandLedgerTest::versionConflict);
        run("invalid transition", DeliveryCommandLedgerTest::invalidTransition);
        run("complete happy path", DeliveryCommandLedgerTest::complete);
        run("cancel releases capacity", DeliveryCommandLedgerTest::cancelReleases);
        run("completed is terminal", DeliveryCommandLedgerTest::completedTerminal);
        run("unknown delivery", DeliveryCommandLedgerTest::unknown);
        run("event sequence", DeliveryCommandLedgerTest::events);
        run("snapshot restore", DeliveryCommandLedgerTest::snapshot);
        run("restored idempotency", DeliveryCommandLedgerTest::restoredIdempotency);
        run("http health", DeliveryCommandLedgerTest::httpHealth);
        run("http command and query", DeliveryCommandLedgerTest::httpCommand);
        run("http method guard", DeliveryCommandLedgerTest::httpMethod);
        System.out.println("PASS " + passed.size() + "/18");
        passed.forEach(name -> System.out.println("  PASS " + name));
    }

    private static void create() {
        var d = new DeliveryCommandLedger.Service().create("c1", "d1", "o1");
        check(d.status() == Status.CREATED && d.version() == 1, "wrong initial state");
    }
    private static void idempotentCreate() {
        var s = new DeliveryCommandLedger.Service();
        var first = s.create("c1", "d1", "o1");
        var second = s.create("c1", "d1", "o1");
        check(first.equals(second) && s.size() == 1 && s.events().size() == 1, "retry was not idempotent");
    }
    private static void commandConflict() {
        var s = new DeliveryCommandLedger.Service(); s.create("c1", "d1", "o1");
        expect(DeliveryCommandLedger.Conflict.class, () -> s.create("c1", "d2", "o2"));
    }
    private static void duplicateOrder() {
        var s = new DeliveryCommandLedger.Service(); s.create("c1", "d1", "o1");
        expect(DeliveryCommandLedger.Conflict.class, () -> s.create("c2", "d2", "o1"));
    }
    private static void assign() {
        var s = new DeliveryCommandLedger.Service(); s.create("c1", "d1", "o1");
        var d = s.assign("c2", "d1", "r1", 1);
        check(d.status() == Status.ASSIGNED && d.version() == 2 && "r1".equals(d.courierId()), "assign failed");
    }
    private static void capacity() {
        var s = new DeliveryCommandLedger.Service(1);
        s.create("c1", "d1", "o1"); s.create("c2", "d2", "o2"); s.assign("c3", "d1", "r1", 1);
        expect(DeliveryCommandLedger.Conflict.class, () -> s.assign("c4", "d2", "r1", 1));
    }
    private static void versionConflict() {
        var s = new DeliveryCommandLedger.Service(); s.create("c1", "d1", "o1"); s.assign("c2", "d1", "r1", 1);
        expect(DeliveryCommandLedger.Conflict.class, () -> s.transition("c3", "d1", Status.PICKED_UP, 1));
    }
    private static void invalidTransition() {
        var s = new DeliveryCommandLedger.Service(); s.create("c1", "d1", "o1");
        expect(DeliveryCommandLedger.Conflict.class, () -> s.transition("c2", "d1", Status.COMPLETED, 1));
    }
    private static void complete() {
        var s = assigned();
        s.transition("c3", "d1", Status.PICKED_UP, 2);
        var d = s.transition("c4", "d1", Status.COMPLETED, 3);
        check(d.status() == Status.COMPLETED && d.version() == 4, "completion failed");
    }
    private static void cancelReleases() {
        var s = new DeliveryCommandLedger.Service(1);
        s.create("c1", "d1", "o1"); s.create("c2", "d2", "o2"); s.assign("c3", "d1", "r1", 1);
        s.transition("c4", "d1", Status.CANCELLED, 2);
        check(s.assign("c5", "d2", "r1", 1).status() == Status.ASSIGNED, "capacity was not released");
    }
    private static void completedTerminal() {
        var s = assigned(); s.transition("c3", "d1", Status.PICKED_UP, 2); s.transition("c4", "d1", Status.COMPLETED, 3);
        expect(DeliveryCommandLedger.Conflict.class, () -> s.transition("c5", "d1", Status.CANCELLED, 4));
    }
    private static void unknown() {
        expect(DeliveryCommandLedger.NotFound.class, () -> new DeliveryCommandLedger.Service().get("missing"));
    }
    private static void events() {
        var s = assigned();
        check(s.events().size() == 2 && s.events().get(0).sequence() == 1 && s.events().get(1).sequence() == 2, "bad sequence");
    }
    private static void snapshot() throws Exception {
        var s = assigned(); var file = Files.createTempFile("delivery-ledger", ".snapshot");
        try { s.snapshot(file); var restored = DeliveryCommandLedger.Service.restore(file); check(restored.get("d1").equals(s.get("d1")) && restored.events().size() == 2, "restore mismatch"); }
        finally { Files.deleteIfExists(file); }
    }
    private static void restoredIdempotency() throws Exception {
        var s = assigned(); var file = Files.createTempFile("delivery-ledger", ".snapshot");
        try { s.snapshot(file); var restored = DeliveryCommandLedger.Service.restore(file); check(restored.assign("c2", "d1", "r1", 1).equals(s.get("d1")), "command replay lost"); }
        finally { Files.deleteIfExists(file); }
    }
    private static void httpHealth() throws Exception {
        try (var api = new DeliveryCommandLedger.Api(new DeliveryCommandLedger.Service(), 0)) {
            api.start(); var response = get(api.port(), "/health"); check(response.statusCode() == 200 && response.body().contains("UP"), "health failed");
        }
    }
    private static void httpCommand() throws Exception {
        try (var api = new DeliveryCommandLedger.Api(new DeliveryCommandLedger.Service(), 0)) {
            api.start();
            var client = HttpClient.newHttpClient();
            var create = client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + api.port() + "/commands/create?commandId=c1&deliveryId=d1&orderId=o1")).POST(HttpRequest.BodyPublishers.noBody()).build(), HttpResponse.BodyHandlers.ofString());
            var query = get(api.port(), "/deliveries?id=d1");
            check(create.statusCode() == 200 && query.statusCode() == 200 && query.body().contains("CREATED"), "http command failed");
        }
    }
    private static void httpMethod() throws Exception {
        try (var api = new DeliveryCommandLedger.Api(new DeliveryCommandLedger.Service(), 0)) {
            api.start(); var response = get(api.port(), "/commands/create?commandId=c1&deliveryId=d1&orderId=o1"); check(response.statusCode() == 405, "method guard failed");
        }
    }

    private static DeliveryCommandLedger.Service assigned() {
        var s = new DeliveryCommandLedger.Service(); s.create("c1", "d1", "o1"); s.assign("c2", "d1", "r1", 1); return s;
    }
    private static HttpResponse<String> get(int port, String path) throws Exception {
        return HttpClient.newHttpClient().send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path)).GET().build(), HttpResponse.BodyHandlers.ofString());
    }
    private static void check(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
    private static void expect(Class<? extends Throwable> type, Checked action) {
        try { action.run(); throw new AssertionError("expected " + type.getSimpleName()); }
        catch (Throwable e) { if (!type.isInstance(e)) throw new AssertionError("expected " + type.getSimpleName() + ", got " + e, e); }
    }
    private static void run(String name, Checked test) throws Exception { test.run(); passed.add(name); }
    @FunctionalInterface private interface Checked { void run() throws Exception; }
}
