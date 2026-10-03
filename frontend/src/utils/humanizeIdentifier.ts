// 场景展示文案兜底（F17）：后端未下发 scene_title/role_label 时，
// 与后端 _humanize_identifier 同语义地转成自然语言词组，保证兜底路径
// 也不露出原始 snake_case id。sessionApi 与 historyApi 共用同一实现，避免再次双份漂移。
export function humanizeIdentifier(value: string): string {
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}
