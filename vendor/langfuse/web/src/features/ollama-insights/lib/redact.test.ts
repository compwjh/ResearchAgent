// @vitest-environment node

import { describe, expect, it } from "vitest";
import {
  formatDetailValue,
  isSensitiveKey,
  redactSensitiveValue,
} from "./redact";

describe("redact: sensitive key detection", () => {
  it("redacts LANGFUSE_SECRET_KEY", () => {
    expect(formatDetailValue({ LANGFUSE_SECRET_KEY: "abc123" })).toContain(
      "[REDACTED]",
    );
  });

  it("redacts LANGFUSE_PUBLIC_KEY", () => {
    expect(formatDetailValue({ LANGFUSE_PUBLIC_KEY: "pk-lf-abc" })).toContain(
      "[REDACTED]",
    );
    expect(isSensitiveKey("LANGFUSE_PUBLIC_KEY")).toBe(true);
  });

  it("redacts AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY", () => {
    expect(formatDetailValue({ AWS_ACCESS_KEY_ID: "AKIA123" })).toContain(
      "[REDACTED]",
    );
    expect(formatDetailValue({ AWS_SECRET_ACCESS_KEY: "shh" })).toContain(
      "[REDACTED]",
    );
  });
});

describe("redact: embedded credentials in values", () => {
  it("redacts embedded sk-lf / pk-lf key values", () => {
    expect(redactSensitiveValue("token=sk-lf-abcdef123456")).toBe(
      "token=[REDACTED]",
    );
    expect(redactSensitiveValue("key=pk-lf-abcdef123456")).toBe(
      "key=[REDACTED]",
    );
  });

  it("redacts Bearer tokens", () => {
    expect(redactSensitiveValue("Bearer abcdef123456")).toBe("Bearer [REDACTED]");
  });
});

describe("redact: recursive redaction", () => {
  it("recurses through nested objects and arrays", () => {
    const result = redactSensitiveValue({
      nested: {
        AWS_SECRET_ACCESS_KEY: "secret-value",
        items: [{ LANGFUSE_SECRET_KEY: "x" }, "Bearer token123456"],
      },
    });
    const json = JSON.stringify(result);
    expect(json).toContain("[REDACTED]");
    expect(json).not.toContain("secret-value");
    expect(json).not.toContain("token123456");
  });
});

describe("redact: business fields are NOT redacted", () => {
  it("leaves business fields untouched", () => {
    const payload = {
      model: "qwen2.5",
      route: "/v1/chat",
      content: "hello there",
      input: "user prompt",
      output: "assistant reply",
      tokens_per_sec: 42.5,
    };
    const json = JSON.stringify(redactSensitiveValue(payload));
    expect(isSensitiveKey("tokens_per_sec")).toBe(false);
    expect(json).toContain("qwen2.5");
    expect(json).toContain("/v1/chat");
    expect(json).toContain("hello there");
    expect(json).toContain("user prompt");
    expect(json).toContain("assistant reply");
    expect(json).toContain("42.5");
    expect(json).not.toContain("[REDACTED]");
  });
});
