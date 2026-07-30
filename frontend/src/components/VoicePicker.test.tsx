import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import VoicePicker from "./VoicePicker";
import type { Voice } from "../lib/types";

afterEach(cleanup);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EN_VOICES: Voice[] = [
  { reference_id: "en-1", label: "Alice (en)", language: "en", sample_url: null },
  { reference_id: "en-2", label: "Bob (en)", language: "en", sample_url: null },
];

const ES_VOICES: Voice[] = [
  { reference_id: "es-1", label: "Carlos (es)", language: "es", sample_url: null },
];

const ZH_VOICES: Voice[] = [
  { reference_id: "zh-1", label: "Wei (zh)", language: "zh", sample_url: null },
];

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe("VoicePicker rendering", () => {
  it("shows a loading message when loading=true", () => {
    render(<VoicePicker voices={[]} value="" onChange={() => {}} loading={true} />);
    expect(screen.getByText(/loading voices/i)).toBeInTheDocument();
  });

  it("shows empty message when loading=false and voices=[]", () => {
    render(<VoicePicker voices={[]} value="" onChange={() => {}} loading={false} />);
    expect(screen.getByText(/no voices available/i)).toBeInTheDocument();
  });

  it("renders a select element with all provided voices as options", () => {
    render(<VoicePicker voices={EN_VOICES} value="en-1" onChange={() => {}} loading={false} />);
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(2);
    expect(options[0]).toHaveValue("en-1");
    expect(options[1]).toHaveValue("en-2");
  });

  it("selects the option matching the value prop", () => {
    render(<VoicePicker voices={EN_VOICES} value="en-2" onChange={() => {}} loading={false} />);
    const select = screen.getByRole("combobox");
    expect(select).toHaveValue("en-2");
  });
});

// ---------------------------------------------------------------------------
// Interaction
// ---------------------------------------------------------------------------

describe("VoicePicker onChange", () => {
  it("calls onChange with the chosen voice_id when user selects an option", async () => {
    const onChange = vi.fn();
    render(<VoicePicker voices={EN_VOICES} value="en-1" onChange={onChange} loading={false} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "en-2");
    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith("en-2");
  });
});

// ---------------------------------------------------------------------------
// Language → voice filtering
//
// The server returns only voices matching the selected language; the frontend
// passes that filtered list directly to VoicePicker.  These tests verify:
//   1. VoicePicker renders only the voices it receives — no cross-language bleed.
//   2. Switching the voices prop (simulating a language change) updates the list.
// ---------------------------------------------------------------------------

describe("language → voice filtering", () => {
  it("renders only English voices when given EN_VOICES", () => {
    render(<VoicePicker voices={EN_VOICES} value="en-1" onChange={() => {}} loading={false} />);
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(2);
    options.forEach((opt) => expect(opt.getAttribute("value")).toMatch(/^en-/));
  });

  it("renders only Spanish voices when given ES_VOICES", () => {
    render(<VoicePicker voices={ES_VOICES} value="es-1" onChange={() => {}} loading={false} />);
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveValue("es-1");
    expect(options[0]).toHaveTextContent("Carlos (es)");
  });

  it("renders only Mandarin voices when given ZH_VOICES", () => {
    render(<VoicePicker voices={ZH_VOICES} value="zh-1" onChange={() => {}} loading={false} />);
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveValue("zh-1");
  });

  it("no cross-language bleed: Spanish options absent when English voices are shown", () => {
    render(<VoicePicker voices={EN_VOICES} value="en-1" onChange={() => {}} loading={false} />);
    const options = screen.getAllByRole("option");
    const ids = options.map((o) => o.getAttribute("value"));
    expect(ids).not.toContain("es-1");
    expect(ids).not.toContain("zh-1");
  });

  it("shows loading state during language transition (voices cleared)", () => {
    // Simulates the moment after language change before voices re-fetch completes.
    render(<VoicePicker voices={[]} value="" onChange={() => {}} loading={true} />);
    expect(screen.getByText(/loading voices/i)).toBeInTheDocument();
    expect(screen.queryByRole("option")).toBeNull();
  });

  it("updates displayed voices when props change (language switch)", () => {
    const { rerender } = render(
      <VoicePicker voices={EN_VOICES} value="en-1" onChange={() => {}} loading={false} />,
    );
    expect(screen.getAllByRole("option")).toHaveLength(2);

    rerender(
      <VoicePicker voices={ES_VOICES} value="es-1" onChange={() => {}} loading={false} />,
    );
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveValue("es-1");
  });
});
