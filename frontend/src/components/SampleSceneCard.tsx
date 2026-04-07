import type { SampleScene } from "../types/app";

type SampleSceneCardProps = {
  scene: SampleScene;
  onSelect: (sceneId: string) => void;
};

export function SampleSceneCard({ scene, onSelect }: SampleSceneCardProps) {
  return (
    <button className="sample-scene-card" type="button" onClick={() => onSelect(scene.id)}>
      <span className="sample-scene-visual">
        <img className="sample-scene-image" src={scene.imageSrc} alt={scene.imageAlt} />
      </span>
      <span className="sample-scene-copy">
        <span className="sample-scene-title">{scene.title}</span>
        <span className="sample-scene-body">{scene.body}</span>
      </span>
    </button>
  );
}
