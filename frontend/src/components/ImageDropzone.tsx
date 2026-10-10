import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { FileUp } from "lucide-react";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 10 * 1024 * 1024;

/** 客户端先于上传做一次同口径校验，错误文案与旧首页逐字一致。 */
function validateImage(file: File): string | null {
  if (!ALLOWED_TYPES.includes(file.type)) {
    return "请上传 JPG、PNG 或 WebP 图片。";
  }

  if (file.size > MAX_BYTES) {
    return "图片需要小于 10 MB。";
  }

  return null;
}

type ImageDropzoneProps = {
  selectedFileName?: string;
  onSelect: (file: File) => void;
  /**
   * 话题 tab 下隐藏可点击面，但 file input 仍留在文档里：上传入口的可访问名
   * 不随 tab 切换消失，route 级测试可以随时按 label 取到它。
   */
  visible?: boolean;
};

/**
 * 点击与拖拽共用一个可点击面（按钮本身），两条入口走同一条校验链路。
 *
 * 按钮名字来自可见文本「点击上传，或把图片拖到这里」，隐藏的 file input 保留同名的
 * aria-label —— 两者名字相近，测试取 input 时需带 `{ selector: "input" }`，
 * 取可点击面时用 `getByRole("button", …)`。
 */
export function ImageDropzone({ selectedFileName = "", onSelect, visible = true }: ImageDropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState("");

  function accept(candidate: File | null | undefined) {
    if (!candidate) {
      return;
    }

    const message = validateImage(candidate);
    if (message) {
      setError(message);
      return;
    }

    setError("");
    onSelect(candidate);
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    accept(event.target.files?.[0]);
  }

  function onDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    setDragOver(false);
    accept(event.dataTransfer.files?.[0]);
  }

  return (
    <div className={visible ? "mt-5" : "sr-only"}>
      {visible ? (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`w-full rounded-3xl border-2 border-dashed p-10 text-center transition-all duration-200 sm:p-12 ${
            dragOver
              ? "scale-[1.01] border-[#131311] bg-[#131311]/5"
              : "border-[#131311]/15 bg-white hover:border-[#131311]/35"
          }`}
        >
          <span className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-[#131311] text-[#d8f34e]">
            <FileUp size={26} aria-hidden="true" />
          </span>
          <span className="font-display mt-4 block text-[19px] font-bold tracking-tight">
            点击上传，或把图片拖到这里
          </span>
          <span className="mt-1 block text-[13px] text-stone-500">
            支持 JPG / PNG / WebP，最大 10 MB。我们会先读场景、定角色，再准备第一句开场提示。
          </span>
          {selectedFileName ? (
            <span className="mt-3 inline-block rounded-full bg-[#131311]/5 px-3 py-1.5 text-[12px] font-semibold text-stone-600">
              {selectedFileName}
            </span>
          ) : null}
          {error ? (
            <span role="alert" className="mt-3 block text-[13px] font-semibold text-rose-600">
              {error}
            </span>
          ) : null}
        </button>
      ) : null}

      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        aria-label="点击上传，或把图片拖到这里"
        accept="image/jpeg,image/png,image/webp"
        onChange={onFileChange}
      />
    </div>
  );
}
