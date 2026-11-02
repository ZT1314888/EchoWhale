import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HomeComposer } from "./HomeComposer";

const SCENE_ALTS = ["咖啡店柜台与点单场景", "办公室内的工作交流场景", "街头出行与问路场景"];

function renderComposer(overrides: Partial<Parameters<typeof HomeComposer>[0]> = {}) {
  const props = {
    selectedSceneId: "coffee",
    onSelectScene: vi.fn(),
    onSelectFile: vi.fn(),
    ...overrides,
  };

  render(<HomeComposer {...props} />);
  return props;
}

describe("HomeComposer", () => {
  it("offers exactly two entrances and no paste tab", () => {
    renderComposer();

    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByRole("tab", { name: /Topics/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Upload/ })).toHaveAttribute("aria-selected", "false");
    expect(screen.queryByRole("tab", { name: /Paste/ })).not.toBeInTheDocument();
  });

  it("lists the three real sample scenes and reports the picked one", () => {
    const props = renderComposer();

    for (const alt of SCENE_ALTS) {
      expect(screen.getByRole("img", { name: alt })).toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: /街头问路/ }));
    expect(props.onSelectScene).toHaveBeenCalledWith("street");
  });

  it("swaps the scene grid for the dropzone when the upload tab is picked", () => {
    const props = renderComposer({ fileName: "counter.png" });
    const file = new File(["image"], "counter.png", { type: "image/png" });

    fireEvent.click(screen.getByRole("tab", { name: /Upload/ }));

    expect(screen.queryByRole("img", { name: SCENE_ALTS[0] })).not.toBeInTheDocument();
    expect(screen.getByText("counter.png")).toBeInTheDocument();

    const dropzone = screen.getByRole("button", { name: /点击上传，或把图片拖到这里/ });
    fireEvent.drop(dropzone, { dataTransfer: { files: [file] } });
    expect(props.onSelectFile).toHaveBeenCalledWith(file);
  });

  it("keeps an invalid drop inside the composer instead of calling back", () => {
    const props = renderComposer();

    fireEvent.click(screen.getByRole("tab", { name: /Upload/ }));
    fireEvent.drop(screen.getByRole("button", { name: /点击上传，或把图片拖到这里/ }), {
      dataTransfer: { files: [new File(["x"], "notes.txt", { type: "text/plain" })] },
    });

    expect(props.onSelectFile).not.toHaveBeenCalled();
    expect(screen.getByText("请上传 JPG、PNG 或 WebP 图片。")).toBeInTheDocument();
  });
});
