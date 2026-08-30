// map-lifecycle.test.jsx
//
// Regression test for the black-map bug: asserts the Leaflet MapContainer
// mounts EXACTLY ONCE across repeated tab switches, and never unmounts when
// the image queue becomes empty. react-leaflet itself is mocked with
// lightweight lifecycle-tracking stand-ins (jsdom can't do Leaflet's real
// tile/DOM measurement work reliably) -- this tests OUR component's mount
// lifecycle directly, which is what the bug actually was.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

let mapContainerMountCount = 0;
let mapContainerCurrentlyMounted = false;
let lastInvalidateSizeCallCount = 0;
const invalidateSize = vi.fn(() => {
  lastInvalidateSizeCallCount += 1;
});
const fakeMapInstance = { invalidateSize, setView: vi.fn(), fitBounds: vi.fn() };

vi.mock("react-leaflet", () => {
  const React = require("react");
  return {
    MapContainer: ({ children }) => {
      React.useEffect(() => {
        mapContainerMountCount += 1;
        mapContainerCurrentlyMounted = true;
        return () => {
          mapContainerCurrentlyMounted = false;
        };
      }, []);
      return <div data-testid="fake-map-container">{children}</div>;
    },
    TileLayer: () => <div data-testid="fake-tile-layer" />,
    Marker: ({ children, eventHandlers }) => (
      <div data-testid="fake-marker" onClick={() => eventHandlers?.click?.()}>{children}</div>
    ),
    Popup: ({ children }) => <div data-testid="fake-popup">{children}</div>,
    ZoomControl: () => <div data-testid="fake-zoom-control" />,
    useMapEvents: () => null,
    useMap: () => fakeMapInstance,
  };
});

vi.mock("leaflet", () => ({
  default: {
    Marker: { prototype: { options: {} } },
    icon: () => ({}),
    divIcon: () => ({}),
    DomEvent: {
      disableClickPropagation: vi.fn(),
      disableScrollPropagation: vi.fn(),
    },
  },
}));

// api.js makes real fetch calls on mount -- stub them out so App doesn't
// hang/error waiting for a real backend during this test.
vi.mock("../api.js", () => ({
  checkHealth: vi.fn().mockResolvedValue(true),
  fetchDisasterTypes: vi.fn().mockResolvedValue([{ value: "earthquake", models_run: ["earthquake", "building"] }]),
  analyzeDisaster: vi.fn(),
  ApiError: class ApiError extends Error {},
  API_BASE_URL: "http://localhost:8000",
}));

const { default: App } = await import("../App.jsx");

describe("Map keep-alive lifecycle (regression test for the black-map bug)", () => {
  beforeEach(() => {
    mapContainerMountCount = 0;
    mapContainerCurrentlyMounted = false;
    lastInvalidateSizeCallCount = 0;
    invalidateSize.mockClear();
  });

  it("mounts the Leaflet map exactly once across many tab switches", async () => {
    render(<App />);

    // Wait for the initial health-check/disaster-types effect to settle.
    await screen.findByRole("button", { name: /^analyze disaster$/i });

    expect(mapContainerMountCount).toBe(1);
    expect(mapContainerCurrentlyMounted).toBe(true);

    const tabs = ["Overview", "Map", "Overview", "Hazard Analysis", "Map", "Model Status", "Map"];
    for (const tabLabel of tabs) {
      const tabButtons = screen.getAllByRole("button", { name: new RegExp(`^${tabLabel}$`, "i") });
      fireEvent.click(tabButtons[0]);
    }

    // THE core regression assertion: no matter how many times we switched
    // tabs, the underlying MapContainer was mounted exactly once -- it was
    // never unmounted and recreated.
    expect(mapContainerMountCount).toBe(1);
    expect(mapContainerCurrentlyMounted).toBe(true);
  });

  it("does not unmount the map when the image queue becomes empty (the actual original bug)", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /^analyze disaster$/i });
    expect(mapContainerMountCount).toBe(1);

    // Upload a file, then remove it -- this is the exact sequence that used
    // to unmount MapPanel's <LocationMap> entirely (queue.length === 0).
    const fileInput = document.querySelector('input[type="file"]');
    const file = new File(["fake"], "test.jpg", { type: "image/jpeg" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    const removeButtons = await screen.findAllByLabelText(/remove test\.jpg/i);
    fireEvent.click(removeButtons[0]);

    // Map must still be exactly the same single instance -- never remounted.
    expect(mapContainerMountCount).toBe(1);
    expect(mapContainerCurrentlyMounted).toBe(true);
  });

  it("calls invalidateSize when switching TO the map tab, not on every render", async () => {
    render(<App />);
    await screen.findByRole("button", { name: /^analyze disaster$/i });

    const mapTabs = screen.getAllByRole("button", { name: /^map$/i });
    fireEvent.click(mapTabs[0]);

    // Allow the double-requestAnimationFrame in VisibilitySync to flush.
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

    expect(invalidateSize).toHaveBeenCalled();
    const callsAfterFirstSwitch = invalidateSize.mock.calls.length;

    // Switching away and back should trigger it again (one call per
    // visibility transition), but switching between OTHER tabs should not
    // call it repeatedly while the map stays hidden.
    const overviewTabs = screen.getAllByRole("button", { name: /^overview$/i });
    fireEvent.click(overviewTabs[0]);
    fireEvent.click(overviewTabs[0]); // no-op, already on overview
    expect(invalidateSize.mock.calls.length).toBe(callsAfterFirstSwitch); // unchanged while map is hidden

    fireEvent.click(mapTabs[0]);
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    expect(invalidateSize.mock.calls.length).toBeGreaterThan(callsAfterFirstSwitch);
  });
});
