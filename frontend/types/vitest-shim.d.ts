declare module "vitest" {
  export function describe(name: string, fn: () => void): void;
  export function it(name: string, fn: () => void): void;
  export function expect<T = unknown>(value: T): {
    toBe(expected: unknown): void;
    toEqual(expected: unknown): void;
    toBeDefined(): void;
    toBeGreaterThan(expected: number): void;
    toBeCloseTo(expected: number, precision?: number): void;
  };
}

declare module "vitest/config" {
  export function defineConfig<T extends Record<string, unknown>>(config: T): T;
}
