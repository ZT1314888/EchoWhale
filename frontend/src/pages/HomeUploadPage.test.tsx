import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }));

vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ status: "anonymous", user: null }),
}));

import { HomeUploadPage } from "./HomeUploadPage";

function renderHome() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <HomeUploadPage />
    </MemoryRouter>,
  );
}

/** 可点击面是按钮本身，名字来自可见文本（隐藏的 file input 另有同名 aria-label）。 */
function getDropzone() {
  fireEvent.click(screen.getByRole("tab", { name: /Upload/ }));
  return screen.getByRole("button", { name: /点击上传，或把图片拖到这里/ });
}

describe("HomeUploadPage dropzone", () => {
  beforeEach(() => {
    navigateMock.mockClear();
  });

  it("navigates to the loading route when a valid image is dropped onto the dropzone", () => {
    renderHome();
    const file = new File(["image"], "coffee.png", { type: "image/png" });

    fireEvent.drop(getDropzone(), { dataTransfer: { files: [file] } });

    // 断言口径与点击上传（onFileChange）一致：同一跳转目标、同一 draft 结构。
    expect(navigateMock).toHaveBeenCalledTimes(1);
    expect(navigateMock).toHaveBeenCalledWith("/session/loading", {
      state: { draft: { source: "file", fileName: "coffee.png", file } },
    });
    expect(screen.getByText("coffee.png")).toBeInTheDocument();
  });

  it("shows the validation error without navigating when a non-image file is dropped", () => {
    renderHome();
    const file = new File(["text"], "notes.txt", { type: "text/plain" });

    fireEvent.drop(getDropzone(), { dataTransfer: { files: [file] } });

    expect(navigateMock).not.toHaveBeenCalled();
    expect(screen.getByText("请上传 JPG、PNG 或 WebP 图片。")).toBeInTheDocument();
  });

  it("defaults to the topic tab and offers the three real sample scenes", () => {
    renderHome();

    expect(screen.getByRole("tab", { name: /Topics/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("img", { name: "咖啡店柜台与点单场景" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "办公室内的工作交流场景" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "街头出行与问路场景" })).toBeInTheDocument();
    // 后端没有 Mode / Level 字段，这两个选择器连同「粘贴」tab 一起被删除。
    expect(screen.queryByRole("tab", { name: /Paste/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/练习模式/)).not.toBeInTheDocument();
  });

  it("starts a real sample session from the topic tab", () => {
    renderHome();

    fireEvent.click(screen.getByRole("button", { name: /街头问路/ }));

    expect(navigateMock).toHaveBeenCalledWith("/session/loading", {
      state: { draft: { source: "sample", sampleSceneId: "street" } },
    });
  });
});
