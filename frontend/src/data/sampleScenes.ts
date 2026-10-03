import type { SampleScene } from "../types/app";
import coffeeSceneImage from "../assets/sample-scenes/coffee.png";
import streetSceneImage from "../assets/sample-scenes/to.png";
import officeSceneImage from "../assets/sample-scenes/work.jpg";

// 首页示例场景是静态产品内容（非 mock 数据）：从 mock 时代的数据文件迁出独立成文件，
// data/ 目录随之收口为仅剩这一份静态内容。
export const sampleScenes: SampleScene[] = [
  {
    id: "coffee",
    title: "咖啡店点单",
    body: "练习点饮料、回应店员，再把语气说得自然一些。",
    imageSrc: coffeeSceneImage,
    imageAlt: "咖啡店柜台与点单场景",
    roleLabel: "角色 · 友好的店员",
    openingPrompt: "开场提示：店员先向你问好。先用一句简短英文回应，把对话顺利打开。",
    tags: ["点单菜单", "轻松语气"],
    liveHint: "先用更短的开场句，再把额外细节放到第二句里，会更稳。",
  },
  {
    id: "office",
    title: "办公室交流",
    body: "练习快速汇报状态、回应一个问题，并保持简洁。",
    imageSrc: officeSceneImage,
    imageAlt: "办公室内的工作交流场景",
    roleLabel: "角色 · 项目同事",
    openingPrompt: "开场提示：同事先问你进度。先回答状态，再补一句下一步动作。",
    tags: ["简短汇报", "工作日常"],
    liveHint: "先说结果，再说原因，会更像真实办公室沟通。",
  },
  {
    id: "street",
    title: "街头问路",
    body: "练习问路、确认路线，再把关键地标清楚地重复出来。",
    imageSrc: streetSceneImage,
    imageAlt: "街头出行与问路场景",
    roleLabel: "角色 · 路人",
    openingPrompt: "开场提示：先用一句英文礼貌发问，再补目的地信息。",
    tags: ["问路确认", "生活场景"],
    liveHint: "先说目的地，再问路线，会更容易得到清晰回复。",
  },
];
