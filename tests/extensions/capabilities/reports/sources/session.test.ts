import { SESSION_TIMEOUT_MINUTES, SessionManager } from "./session";

describe("SessionManager", () => {
  const manager = new SessionManager();

  it("expires after 15 minutes", () => {
    expect(manager.isExpired(16)).toBe(true);
    expect(manager.isExpired(15)).toBe(false);
  });

  describe("when idle", () => {
    it.each([1, 15])("stays active at %d minutes", (minutes) => {
      expect(manager.isExpired(minutes)).toBe(false);
    });
  });

  it.skip("remembers the device", () => {
    expect(true).toBe(false);
  });
});

test("the limit is 15", () => {
  expect(SESSION_TIMEOUT_MINUTES).toBe(15);
});

test("this one fails", () => {
  expect(1).toBe(2);
});
