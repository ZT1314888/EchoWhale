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

function getDropzone(container: HTMLElement): Element {
  const dropzone = container.querySelector(".dropzone-card");
  if (!dropzone) {
    throw new Error("dropzone card not found");
  }
  return dropzone;
}

describe("HomeUploadPage dropzone", () => {
  beforeEach(() => {
    navigateMock.mockClear();
  });

  it("navigates to the loading route when a valid image is dropped onto the dropzone", () => {
    const { container } = renderHome();
    const file = new File(["image"], "coffee.png", { type: "image/png" });

    fireEvent.drop(getDropzone(container), { dataTransfer: { files: [file] } });

    // 断言口径与点击上传（onFileChange）一致：同一跳转目标、同一 draft 结构。
    expect(navigateMock).toHaveBeenCalledTimes(1);
    expect(navigateMock).toHaveBeenCalledWith("/session/loading", {
      state: { draft: { source: "file", fileName: "coffee.png", file } },
    });
    expect(screen.getByText("coffee.png")).toBeInTheDocument();
  });

  it("shows the validation error without navigating when a non-image file is dropped", () => {
    const { container } = renderHome();
    const file = new File(["text"], "notes.txt", { type: "text/plain" });

    fireEvent.drop(getDropzone(container), { dataTransfer: { files: [file] } });

    expect(navigateMock).not.toHaveBeenCalled();
    expect(screen.getByText("请上传 JPG、PNG 或 WebP 图片。")).toBeInTheDocument();
  });
});
