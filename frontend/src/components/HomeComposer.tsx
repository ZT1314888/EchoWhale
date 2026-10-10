import { useState } from "react";
import { FileUp, LayoutGrid } from "lucide-react";

import { sampleScenes } from "../data/sampleScenes";
import { ImageDropzone } from "./ImageDropzone";
import { SampleSceneCard } from "./SampleSceneCard";

type SourceTab = "topic" | "upload";

const TABS = [
  { id: "topic" as const, icon: LayoutGrid, label: "Topics", cn: "话题" },
  { id: "upload" as const, icon: FileUp, label: "Upload", cn: "上传" },
];

type HomeComposerProps = {
  selectedSceneId: string;
  onSelectScene: (sampleSceneId: string) => void;
  onSelectFile: (file: File) => void;
  fileName?: string;
};

/**
 * 首页创作器的两段式入口：话题（示例场景）与上传（图片）。
 *
 * 原型的第三个「粘贴文本」tab 已删除：后端没有文本入口，留一个点了没用的输入框
 * 比没有更糟。Mode / Level 选择器同理删除，后端没有这两个字段。
 */
export function HomeComposer({ selectedSceneId, onSelectScene, onSelectFile, fileName = "" }: HomeComposerProps) {
  const [tab, setTab] = useState<SourceTab>("topic");

  return (
    <div className="rounded-[28px] border border-[#131311]/8 bg-[#faf9f6] p-6 shadow-sm sm:p-7">
      <div className="grid grid-cols-2 gap-1.5 rounded-2xl bg-[#131311]/5 p-1.5" role="tablist" aria-label="练习来源">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={`flex items-center justify-center gap-1.5 rounded-xl px-3 py-3 text-[13px] font-bold transition-all duration-200 ${
              tab === item.id ? "bg-[#131311] text-white shadow-lg" : "text-stone-500 hover:bg-white hover:text-[#131311]"
            }`}
          >
            <item.icon size={15} aria-hidden="true" />
            {item.label}
            <span
              aria-hidden="true"
              className={`text-[11px] font-normal ${tab === item.id ? "text-white/50" : "text-stone-400"}`}
            >
              {item.cn}
            </span>
          </button>
        ))}
      </div>

      {tab === "topic" ? (
        <div className="stagger mt-5 grid gap-2.5 sm:grid-cols-2">
          {sampleScenes.map((scene) => (
            <SampleSceneCard
              key={scene.id}
              scene={scene}
              active={selectedSceneId === scene.id}
              onSelect={onSelectScene}
            />
          ))}
        </div>
      ) : null}

      {/* dropzone 挂载但只在 Upload tab 可见：上传入口的 label 不随 tab 消失。 */}
      <ImageDropzone selectedFileName={fileName} onSelect={onSelectFile} visible={tab === "upload"} />
    </div>
  );
}
