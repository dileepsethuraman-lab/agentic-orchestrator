package com.telecom.orchestrator.store;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
public class SubscriberLock {
    private static final Logger log = LoggerFactory.getLogger(SubscriberLock.class);
    private static final int LOCK_TTL = 30;
    private static final int RETRY_DELAY_MS = 100;
    private static final int MAX_RETRIES = 50;

    private final JdbcTemplate db;

    public SubscriberLock(JdbcTemplate db) {
        this.db = db;
        db.execute("CREATE TABLE IF NOT EXISTS subscriber_locks (lock_key VARCHAR(255) PRIMARY KEY, worker_id VARCHAR(100), acquired_at BIGINT, expire_at BIGINT)");
    }

    public boolean tryAcquire(String subscriberId, String workerId) {
        String lockKey = "lock:sub:" + subscriberId;
        for (int i = 0; i < MAX_RETRIES; i++) {
            long now = System.currentTimeMillis() / 1000;

            // Check existing lock
            var rows = db.queryForList("SELECT worker_id, expire_at FROM subscriber_locks WHERE lock_key = ?", lockKey);
            if (rows.isEmpty()) {
                db.update("INSERT INTO subscriber_locks (lock_key, worker_id, acquired_at, expire_at) VALUES (?,?,?,?)",
                        lockKey, workerId, now, now + LOCK_TTL);
                return true;
            }

            var row = rows.get(0);
            Long expireAt = (Long) row.get("expire_at");
            String existingWorker = (String) row.get("worker_id");

            // Expired lock — steal it
            if (now > expireAt) {
                db.update("UPDATE subscriber_locks SET worker_id=?, acquired_at=?, expire_at=? WHERE lock_key=?",
                        workerId, now, now + LOCK_TTL, lockKey);
                return true;
            }

            // Re-entrant
            if (workerId.equals(existingWorker)) {
                return true;
            }

            // Wait and retry
            try { Thread.sleep(RETRY_DELAY_MS); } catch (InterruptedException e) { Thread.currentThread().interrupt(); return false; }
        }
        return false;
    }

    public void release(String subscriberId, String workerId) {
        String lockKey = "lock:sub:" + subscriberId;
        db.update("DELETE FROM subscriber_locks WHERE lock_key = ? AND worker_id = ?", lockKey, workerId);
    }

    public void forceRelease(String subscriberId) {
        String lockKey = "lock:sub:" + subscriberId;
        db.update("DELETE FROM subscriber_locks WHERE lock_key = ?", lockKey);
    }
}
