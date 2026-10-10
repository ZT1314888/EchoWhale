import { Check } from "lucide-react";

import type { SampleScene } from "../types/app";

type SampleSceneCardProps = {
  scene: SampleScene;
  active?: boolean;
  onSelect: (sceneId: string) => void;
};

/**
 * 示例场景卡：视觉照搬原型的话题按钮，数据仍是 EchoWhale 真实的三个示例场景。
 * 缩略图始终用真实的场景图片，选中态在图上盖一层 lime 与对勾，避免切换时图片闪失。
 */
export function SampleSceneCard({ scene, active = false, onSelect }: SampleSceneCardProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(scene.id)}
      className={`group flex items-center gap-3.5 rounded-2xl border p-3.5 text-left transition-all duration-200 ${
        active
          ? "border-[#131311] bg-[#131311] text-white shadow-[0_16px_32px_-16px_rgba(19,19,17,0.5)]"
          : "border-[#131311]/8 bg-white hover:border-[#131311]/25"
      }`}
    >
      <span
        className={`relative grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-xl transition ${
          active ? "ring-2 ring-[#131311]" : "group-hover:ring-2 group-hover:ring-[#131311]/30"
        }`}
      >
        <img className="h-11 w-11 object-cover" src={scene.imageSrc} alt={scene.imageAlt} />
        {active ? (
          <span className="absolute inset-0 grid place-items-center bg-[#d8f34e]/85 text-[#131311]">
            <Check size={19} strokeWidth={3} aria-hidden="true" />
          </span>
        ) : null}
      </span>

      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13.5px] font-bold">
          {scene.title}
          <span
            aria-hidden="true"
            className={`ml-1 text-[11px] font-normal ${active ? "text-white/50" : "text-stone-400"}`}
          >
            {scene.roleLabel.replace("角色 · ", "")}
          </span>
        </span>
        <span className={`block truncate text-[11.5px] ${active ? "text-white/55" : "text-stone-400"}`}>
          {scene.body}
        </span>
      </span>
    </button>
  );
}
