package lab.delivery;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Dependency-free command ledger for a synthetic last-mile delivery service. */
public final class DeliveryCommandLedger {
    private DeliveryCommandLedger() {}

    public enum Status { CREATED, ASSIGNED, PICKED_UP, COMPLETED, CANCELLED }

    public record Delivery(String id, String orderId, String courierId, Status status, long version) {}
    public record Event(long sequence, String deliveryId, String type, long version, Instant occurredAt) {}
    private record CommandResult(String fingerprint, Delivery delivery) {}

    public static final class Service {
        private final Map<String, Delivery> deliveries = new LinkedHashMap<>();
        private final Map<String, String> orderOwners = new LinkedHashMap<>();
        private final Map<String, CommandResult> commands = new LinkedHashMap<>();
        private final List<Event> events = new ArrayList<>();
        private final int courierCapacity;
        private long sequence;

        public Service() { this(3); }
        public Service(int courierCapacity) {
            if (courierCapacity < 1) throw new IllegalArgumentException("courier capacity must be positive");
            this.courierCapacity = courierCapacity;
        }

        public synchronized Delivery create(String commandId, String deliveryId, String orderId) {
            String fingerprint = "CREATE|" + required(deliveryId, "deliveryId") + "|" + required(orderId, "orderId");
            Delivery replay = replay(commandId, fingerprint);
            if (replay != null) return replay;
            if (deliveries.containsKey(deliveryId)) throw new Conflict("delivery already exists");
            if (orderOwners.containsKey(orderId)) throw new Conflict("order already has a delivery");
            Delivery delivery = new Delivery(deliveryId, orderId, null, Status.CREATED, 1);
            deliveries.put(deliveryId, delivery);
            orderOwners.put(orderId, deliveryId);
            append(delivery, "DELIVERY_CREATED");
            commands.put(commandId, new CommandResult(fingerprint, delivery));
            return delivery;
        }

        public synchronized Delivery assign(String commandId, String deliveryId, String courierId, long expectedVersion) {
            String fingerprint = "ASSIGN|" + required(deliveryId, "deliveryId") + "|" + required(courierId, "courierId") + "|" + expectedVersion;
            Delivery replay = replay(commandId, fingerprint);
            if (replay != null) return replay;
            Delivery current = requireDelivery(deliveryId);
            requireVersion(current, expectedVersion);
            if (current.status() != Status.CREATED) throw new Conflict("only CREATED deliveries can be assigned");
            long active = deliveries.values().stream()
                    .filter(d -> courierId.equals(d.courierId()))
                    .filter(d -> d.status() == Status.ASSIGNED || d.status() == Status.PICKED_UP)
                    .count();
            if (active >= courierCapacity) throw new Conflict("courier capacity exceeded");
            Delivery next = new Delivery(current.id(), current.orderId(), courierId, Status.ASSIGNED, current.version() + 1);
            store(commandId, fingerprint, next, "COURIER_ASSIGNED");
            return next;
        }

        public synchronized Delivery transition(String commandId, String deliveryId, Status target, long expectedVersion) {
            Objects.requireNonNull(target, "target");
            String fingerprint = "TRANSITION|" + required(deliveryId, "deliveryId") + "|" + target + "|" + expectedVersion;
            Delivery replay = replay(commandId, fingerprint);
            if (replay != null) return replay;
            Delivery current = requireDelivery(deliveryId);
            requireVersion(current, expectedVersion);
            if (!allowed(current.status(), target)) throw new Conflict("invalid transition " + current.status() + " -> " + target);
            Delivery next = new Delivery(current.id(), current.orderId(), current.courierId(), target, current.version() + 1);
            store(commandId, fingerprint, next, "STATUS_" + target);
            return next;
        }

        public synchronized Delivery get(String deliveryId) { return requireDelivery(deliveryId); }
        public synchronized List<Event> events() { return List.copyOf(events); }
        public synchronized int size() { return deliveries.size(); }

        public synchronized void snapshot(Path target) throws IOException {
            Path parent = target.toAbsolutePath().getParent();
            if (parent != null) Files.createDirectories(parent);
            Path temp = target.resolveSibling(target.getFileName() + ".tmp");
            List<String> lines = new ArrayList<>();
            lines.add("META|" + courierCapacity + "|" + sequence);
            for (Delivery d : deliveries.values()) {
                lines.add("DELIVERY|" + enc(d.id()) + "|" + enc(d.orderId()) + "|" + enc(d.courierId()) + "|" + d.status() + "|" + d.version());
            }
            for (Map.Entry<String, CommandResult> entry : commands.entrySet()) {
                Delivery d = entry.getValue().delivery();
                lines.add("COMMAND|" + enc(entry.getKey()) + "|" + enc(entry.getValue().fingerprint()) + "|" + enc(d.id()));
            }
            for (Event e : events) {
                lines.add("EVENT|" + e.sequence() + "|" + enc(e.deliveryId()) + "|" + enc(e.type()) + "|" + e.version() + "|" + e.occurredAt());
            }
            Files.write(temp, lines, StandardCharsets.UTF_8);
            try {
                Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (java.nio.file.AtomicMoveNotSupportedException ignored) {
                Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
            }
        }

        public static Service restore(Path source) throws IOException {
            List<String> lines = Files.readAllLines(source, StandardCharsets.UTF_8);
            if (lines.isEmpty() || !lines.getFirst().startsWith("META|")) throw new IOException("invalid snapshot");
            String[] meta = lines.getFirst().split("\\|", -1);
            Service service = new Service(Integer.parseInt(meta[1]));
            service.sequence = Long.parseLong(meta[2]);
            Map<String, String[]> rawCommands = new LinkedHashMap<>();
            for (String line : lines.subList(1, lines.size())) {
                String[] p = line.split("\\|", -1);
                switch (p[0]) {
                    case "DELIVERY" -> {
                        Delivery d = new Delivery(dec(p[1]), dec(p[2]), dec(p[3]), Status.valueOf(p[4]), Long.parseLong(p[5]));
                        service.deliveries.put(d.id(), d);
                        service.orderOwners.put(d.orderId(), d.id());
                    }
                    case "COMMAND" -> rawCommands.put(dec(p[1]), new String[]{dec(p[2]), dec(p[3])});
                    case "EVENT" -> service.events.add(new Event(Long.parseLong(p[1]), dec(p[2]), dec(p[3]), Long.parseLong(p[4]), Instant.parse(p[5])));
                    default -> throw new IOException("unknown snapshot record");
                }
            }
            for (Map.Entry<String, String[]> entry : rawCommands.entrySet()) {
                Delivery d = service.deliveries.get(entry.getValue()[1]);
                if (d == null) throw new IOException("command references missing delivery");
                service.commands.put(entry.getKey(), new CommandResult(entry.getValue()[0], d));
            }
            return service;
        }

        private Delivery replay(String commandId, String fingerprint) {
            required(commandId, "commandId");
            CommandResult previous = commands.get(commandId);
            if (previous == null) return null;
            if (!previous.fingerprint().equals(fingerprint)) throw new Conflict("command id reused with different payload");
            return previous.delivery();
        }

        private void store(String commandId, String fingerprint, Delivery next, String eventType) {
            deliveries.put(next.id(), next);
            append(next, eventType);
            commands.put(commandId, new CommandResult(fingerprint, next));
        }

        private void append(Delivery delivery, String type) {
            events.add(new Event(++sequence, delivery.id(), type, delivery.version(), Instant.now()));
        }

        private Delivery requireDelivery(String id) {
            Delivery delivery = deliveries.get(required(id, "deliveryId"));
            if (delivery == null) throw new NotFound("delivery not found");
            return delivery;
        }

        private static void requireVersion(Delivery delivery, long expected) {
            if (delivery.version() != expected) throw new Conflict("version conflict: expected " + expected + ", actual " + delivery.version());
        }

        private static boolean allowed(Status from, Status to) {
            return (from == Status.CREATED && to == Status.CANCELLED)
                    || (from == Status.ASSIGNED && (to == Status.PICKED_UP || to == Status.CANCELLED))
                    || (from == Status.PICKED_UP && (to == Status.COMPLETED || to == Status.CANCELLED));
        }
    }

    public static final class Api implements AutoCloseable {
        private final Service service;
        private final HttpServer server;

        public Api(Service service, int port) throws IOException {
            this.service = service;
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
            server.createContext("/health", exchange -> respond(exchange, 200, "{\"status\":\"UP\"}"));
            server.createContext("/deliveries", this::deliveries);
            server.createContext("/events", this::events);
            server.createContext("/commands/create", exchange -> command(exchange, "create"));
            server.createContext("/commands/assign", exchange -> command(exchange, "assign"));
            server.createContext("/commands/transition", exchange -> command(exchange, "transition"));
        }

        public void start() { server.start(); }
        public int port() { return server.getAddress().getPort(); }
        @Override public void close() { server.stop(0); }

        private void deliveries(HttpExchange exchange) throws IOException {
            try {
                method(exchange, "GET");
                Delivery d = service.get(params(exchange).get("id"));
                respond(exchange, 200, json(d));
            } catch (RuntimeException e) { failure(exchange, e); }
        }

        private void events(HttpExchange exchange) throws IOException {
            try {
                method(exchange, "GET");
                StringBuilder out = new StringBuilder("[\n");
                List<Event> events = service.events();
                for (int i = 0; i < events.size(); i++) {
                    Event e = events.get(i);
                    out.append("  {\"sequence\":").append(e.sequence()).append(",\"deliveryId\":\"").append(escape(e.deliveryId()))
                            .append("\",\"type\":\"").append(escape(e.type())).append("\",\"version\":").append(e.version()).append("}");
                    if (i + 1 < events.size()) out.append(',');
                    out.append('\n');
                }
                respond(exchange, 200, out.append(']').toString());
            } catch (RuntimeException e) { failure(exchange, e); }
        }

        private void command(HttpExchange exchange, String type) throws IOException {
            try {
                method(exchange, "POST");
                Map<String, String> p = params(exchange);
                Delivery d = switch (type) {
                    case "create" -> service.create(p.get("commandId"), p.get("deliveryId"), p.get("orderId"));
                    case "assign" -> service.assign(p.get("commandId"), p.get("deliveryId"), p.get("courierId"), number(p, "expectedVersion"));
                    default -> service.transition(p.get("commandId"), p.get("deliveryId"), Status.valueOf(required(p.get("target"), "target")), number(p, "expectedVersion"));
                };
                respond(exchange, 200, json(d));
            } catch (RuntimeException e) { failure(exchange, e); }
        }

        private static void method(HttpExchange exchange, String expected) {
            if (!expected.equals(exchange.getRequestMethod())) throw new MethodNotAllowed("method not allowed");
        }

        private static long number(Map<String, String> p, String key) {
            try { return Long.parseLong(required(p.get(key), key)); }
            catch (NumberFormatException e) { throw new IllegalArgumentException(key + " must be a number"); }
        }

        private static Map<String, String> params(HttpExchange exchange) {
            Map<String, String> values = new LinkedHashMap<>();
            String raw = exchange.getRequestURI().getRawQuery();
            if (raw == null || raw.isBlank()) return values;
            for (String pair : raw.split("&")) {
                String[] part = pair.split("=", 2);
                values.put(url(part[0]), part.length == 2 ? url(part[1]) : "");
            }
            return values;
        }

        private static void failure(HttpExchange exchange, RuntimeException e) throws IOException {
            int status = e instanceof NotFound ? 404 : e instanceof MethodNotAllowed ? 405 : e instanceof Conflict ? 409 : 400;
            respond(exchange, status, "{\"error\":\"" + escape(e.getMessage()) + "\"}");
        }

        private static void respond(HttpExchange exchange, int status, String body) throws IOException {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (var out = exchange.getResponseBody()) { out.write(bytes); }
        }
    }

    public static final class Conflict extends RuntimeException { public Conflict(String message) { super(message); } }
    public static final class NotFound extends RuntimeException { public NotFound(String message) { super(message); } }
    public static final class MethodNotAllowed extends RuntimeException { public MethodNotAllowed(String message) { super(message); } }

    private static String required(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
        return value;
    }
    private static String enc(String value) {
        if (value == null) return "-";
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }
    private static String dec(String value) {
        if ("-".equals(value)) return null;
        return new String(Base64.getUrlDecoder().decode(value), StandardCharsets.UTF_8);
    }
    private static String url(String value) { return URLDecoder.decode(value, StandardCharsets.UTF_8); }
    private static String escape(String value) { return String.valueOf(value).replace("\\", "\\\\").replace("\"", "\\\""); }
    private static String json(Delivery d) {
        return "{\"id\":\"" + escape(d.id()) + "\",\"orderId\":\"" + escape(d.orderId()) + "\",\"courierId\":"
                + (d.courierId() == null ? "null" : "\"" + escape(d.courierId()) + "\"")
                + ",\"status\":\"" + d.status() + "\",\"version\":" + d.version() + "}";
    }

    public static void main(String[] args) throws Exception {
        Service service = new Service();
        Api api = new Api(service, args.length == 0 ? 8080 : Integer.parseInt(args[0]));
        api.start();
        System.out.println("DeliveryCommandLedger listening on http://127.0.0.1:" + api.port());
    }
}
