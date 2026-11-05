package com.example.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class BrokenRuleTest {
    @Test
    void thisOneFails() {
        assertEquals(1, 2);
    }
}
