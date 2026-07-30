/**
 * Recorder state machine tests.
 *
 * Real MediaRecorder / getUserMedia aren't available under jsdom, so we
 * install lightweight fakes on `globalThis` before each test. The fakes
 * expose the same async surface the hook consumes and let us drive
 * lifecycle events (dataavailable, stop, error) synchronously.
 */

import { act, renderHook } from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { useRecorder } from "./useRecorder";

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

class FakeTrack {
  stopped = false;
  stop() {
    this.stopped = true;
  }
}

class FakeStream {
  tracks: FakeTrack[];
  constructor(n = 1) {
    this.tracks = Array.from({ length: n }, () => new FakeTrack());
  }
  getTracks() {
    return this.tracks;
  }
}

interface FakeBlobEvent {
  data: Blob;
}

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];
  static isTypeSupported = vi.fn().mockReturnValue(true);

  state: "inactive" | "recording" | "paused" = "inactive";
  mimeType: string;
  ondataavailable: ((e: FakeBlobEvent) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  stream: FakeStream;

  constructor(stream: FakeStream, opts?: { mimeType?: string }) {
    this.stream = stream;
    this.mimeType = opts?.mimeType ?? "audio/webm;codecs=opus";
    FakeMediaRecorder.instances.push(this);
  }

  start() {
    this.state = "recording";
  }

  stop() {
    if (this.state === "inactive") return;
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["chunk"], { type: this.mimeType }) });
    this.onstop?.();
  }

  triggerError() {
    this.onerror?.();
  }
}

let mockGetUserMedia: ReturnType<typeof vi.fn>;

function installFakes(opts?: { deny?: boolean; constructorThrows?: boolean }) {
  FakeMediaRecorder.instances = [];

  mockGetUserMedia = vi.fn(async () => {
    if (opts?.deny) throw new Error("Permission denied");
    return new FakeStream() as unknown as MediaStream;
  });

  Object.defineProperty(globalThis.navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: mockGetUserMedia },
  });

  if (opts?.constructorThrows) {
    (globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder =
      class {
        static isTypeSupported = () => false;
        constructor() {
          throw new Error("unsupported");
        }
      };
  } else {
    (globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder =
      FakeMediaRecorder;
  }

  // jsdom lacks URL.createObjectURL.
  if (typeof URL.createObjectURL !== "function") {
    URL.createObjectURL = vi.fn(() => "blob:fake");
  } else {
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake");
  }
  if (typeof URL.revokeObjectURL !== "function") {
    URL.revokeObjectURL = vi.fn();
  } else {
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  }
}

beforeEach(() => {
  vi.useFakeTimers();
  installFakes();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// State transitions
// ---------------------------------------------------------------------------

describe("useRecorder — state transitions", () => {
  it("starts in idle", () => {
    const { result } = renderHook(() => useRecorder());
    expect(result.current.state).toBe("idle");
    expect(result.current.blob).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("idle → recording after start()", async () => {
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });

    expect(result.current.state).toBe("recording");
    expect(FakeMediaRecorder.instances).toHaveLength(1);
    expect(FakeMediaRecorder.instances[0].state).toBe("recording");
  });

  it("recording → stopped after stop() and emits a blob", async () => {
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });
    act(() => {
      result.current.stop();
    });

    expect(result.current.state).toBe("stopped");
    expect(result.current.blob).toBeInstanceOf(Blob);
    expect(result.current.blob?.size).toBeGreaterThan(0);
    expect(result.current.blobUrl).toBe("blob:fake");
  });

  it("stopped → idle after reset() and clears the blob", async () => {
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });
    act(() => {
      result.current.stop();
    });
    act(() => {
      result.current.reset();
    });

    expect(result.current.state).toBe("idle");
    expect(result.current.blob).toBeNull();
    expect(result.current.blobUrl).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake");
  });

  it("start() while stopped discards the previous blob", async () => {
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });
    act(() => {
      result.current.stop();
    });
    expect(result.current.blob).not.toBeNull();

    await act(async () => {
      await result.current.start();
    });
    expect(result.current.state).toBe("recording");
    expect(result.current.blob).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Auto-stop on max clip length
// ---------------------------------------------------------------------------

describe("useRecorder — max clip length", () => {
  it("auto-stops when elapsed reaches maxDurationMs", async () => {
    const { result } = renderHook(() => useRecorder({ maxDurationMs: 5000 }));

    await act(async () => {
      await result.current.start();
    });
    expect(result.current.state).toBe("recording");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(result.current.state).toBe("stopped");
    expect(result.current.blob).toBeInstanceOf(Blob);
  });

  it("does not auto-stop before the cap", async () => {
    const { result } = renderHook(() => useRecorder({ maxDurationMs: 10_000 }));

    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(result.current.state).toBe("recording");
    expect(result.current.elapsedMs).toBeGreaterThan(0);
  });

  it("clears the auto-stop timer when the user stops manually", async () => {
    const { result } = renderHook(() => useRecorder({ maxDurationMs: 5000 }));

    await act(async () => {
      await result.current.start();
    });
    act(() => {
      result.current.stop();
    });

    // Advancing past the cap should not re-fire any transitions.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(result.current.state).toBe("stopped");
    // The recorder instance should still be inactive; no additional recorders created.
    expect(FakeMediaRecorder.instances).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Error paths
// ---------------------------------------------------------------------------

describe("useRecorder — errors", () => {
  it("transitions to error when the mic is denied", async () => {
    installFakes({ deny: true });
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });

    expect(result.current.state).toBe("error");
    expect(result.current.error).toMatch(/denied/i);
  });

  it("transitions to error when MediaRecorder constructor throws", async () => {
    installFakes({ constructorThrows: true });
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });

    expect(result.current.state).toBe("error");
    expect(result.current.error).toBeTruthy();
  });

  it("recorder.onerror moves to error and stops the stream", async () => {
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });

    const rec = FakeMediaRecorder.instances[0];
    const tracks = rec.stream.getTracks();

    act(() => {
      rec.triggerError();
    });

    expect(result.current.state).toBe("error");
    expect(tracks.every((t) => t.stopped)).toBe(true);
  });

  it("reset() from error state returns to idle", async () => {
    installFakes({ deny: true });
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.state).toBe("idle");
    expect(result.current.error).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Stream cleanup
// ---------------------------------------------------------------------------

describe("useRecorder — stream cleanup", () => {
  it("stops all MediaStream tracks on stop()", async () => {
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });
    const tracks = FakeMediaRecorder.instances[0].stream.getTracks();
    expect(tracks.every((t) => t.stopped)).toBe(false);

    act(() => {
      result.current.stop();
    });

    expect(tracks.every((t) => t.stopped)).toBe(true);
  });

  it("stops tracks on unmount", async () => {
    const { result, unmount } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });
    const tracks = FakeMediaRecorder.instances[0].stream.getTracks();

    unmount();

    expect(tracks.every((t) => t.stopped)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// MIME selection
// ---------------------------------------------------------------------------

describe("useRecorder — mime selection", () => {
  it("prefers audio/webm;codecs=opus when supported", async () => {
    FakeMediaRecorder.isTypeSupported.mockImplementation(
      (t: string) => t === "audio/webm;codecs=opus",
    );
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.start();
    });

    expect(FakeMediaRecorder.instances[0].mimeType).toBe(
      "audio/webm;codecs=opus",
    );
    expect(result.current.mimeType).toBe("audio/webm;codecs=opus");
  });
});

// ---------------------------------------------------------------------------
// Elapsed reporting
// ---------------------------------------------------------------------------

describe("useRecorder — elapsed", () => {
  it("updates elapsedMs while recording", async () => {
    const { result } = renderHook(() => useRecorder({ maxDurationMs: 30_000 }));

    await act(async () => {
      await result.current.start();
    });
    expect(result.current.elapsedMs).toBe(0);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    expect(result.current.elapsedMs).toBeGreaterThan(0);
  });
});
