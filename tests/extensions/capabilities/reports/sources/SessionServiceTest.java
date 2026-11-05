package com.example.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class SessionServiceTest {
    private final SessionService service = new SessionService();

    @Test
    void timeoutIsFifteenMinutes() {
        assertEquals(Duration.ofMinutes(15), SessionService.TIMEOUT);
    }

    @Test
    @DisplayName("una sesion de 16 minutos expira")
    void expiresAfterTheLimit() {
        assertTrue(service.isExpired(Duration.ofMinutes(16)));
    }

    @ParameterizedTest
    @ValueSource(longs = {1, 15})
    void staysActiveWithinTheLimit(long minutes) {
        assertFalse(service.isExpired(Duration.ofMinutes(minutes)));
    }

    @Test
    @Disabled("not yet")
    void rememberMeIsNotImplemented() {
        assertTrue(false);
    }

    @ParameterizedTest(name = "active at {0} minutes")
    @ValueSource(longs = {2, 3})
    void namedVariants(long minutes) {
        assertFalse(service.isExpired(Duration.ofMinutes(minutes)));
    }

    @Nested
    class WhenIdle {
        @Test
        void aMinuteMoreExpires() {
            assertTrue(service.isExpired(SessionService.TIMEOUT.plusMinutes(1)));
        }
    }
}
