import { describe, expect, it } from 'vitest';
import { resize } from 'no-such-native-module';

describe('Thumbnails', () => {
  it('keeps the ratio', () => {
    expect(resize(2, 1)).toBe(2);
  });
});
