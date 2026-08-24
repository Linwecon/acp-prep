/* ============================================================
   ACP — Global namespace & shared mutable state
   ============================================================ */
window.ACP = {
    EXAM_SINGLE: 50,
    EXAM_MULTI: 25,
    EXAM_TIME: 120 * 60,

    /* 新版官方大纲：知识域 → 章节映射（试题比例 %）+ 大纲详情 */
    EXAM_DOMAINS: [
        {
            id: 'dev', name: '大模型应用开发', pct: 17, chs: ['1', '9', '10', '12'],
            groups: [{
                title: 'API 调用与对话',
                points: [
                    '通过 OpenAI API 调用大模型',
                    '通过 LlamaIndex 向通义千问提问',
                    '基本 API 参数如 model、temperature、top_p 等等',
                    '批量生成与流式生成',
                    '理解消息与对话历史'
                ]
            }]
        },
        {
            id: 'prompt', name: '大模型提示词工程', pct: 15, chs: ['2'],
            groups: [
                {
                    title: '构建有效的提示词',
                    points: [
                        '提示词框架，如提示词要素、提示词分隔符、提示词模板',
                        '理解系统角色提示词的作用'
                    ]
                },
                {
                    title: '利用大模型创建算法应用',
                    points: [
                        '理解大模型的适用场景',
                        '大模型算法实验，如批量对员工咨询做意图分类、用大模型做文档审阅、实现针对问题的自动文档修订'
                    ]
                }
            ]
        },
        {
            id: 'rag', name: '大模型检索增强', pct: 20, chs: ['3'],
            groups: [
                {
                    title: '通过 LlamaIndex 构建 RAG 应用的基本使用方法',
                    points: [
                        '理解 RAG 的核心要素，如文件解析、文本切片、段落召回、段落重排序',
                        '理解对 RAG 做召回优化，如句子窗口检索、自动合并检索等等'
                    ]
                },
                {
                    title: '持续优化检索增强能力',
                    points: [
                        '理解更贴近实战的 RAG 优化方法，如优化文本解析、标题改写优化、表格内容增强、文本分割方法对比等等'
                    ]
                },
                {
                    title: '对检索增强的能力做自动化评测',
                    points: [
                        '了解 RAGAS 指标体系',
                        '懂得 RAG 系统的评测方法'
                    ]
                }
            ]
        },
        {
            id: 'ft', name: '大模型微调', pct: 16, chs: ['5'],
            groups: [
                {
                    title: '大模型的微调',
                    points: ['模型微调的作用、前提、基本步骤、常用算法']
                },
                {
                    title: '微调的实验与评测',
                    points: ['微调数据集构建、微调参数介绍、微调模型评测']
                }
            ]
        },
        {
            id: 'agent', name: '多Agent及多模态应用', pct: 16, chs: ['4', '11'],
            groups: [
                {
                    title: '基于百炼 Assistant API 构建智能体',
                    points: [
                        '理解智能体运行机制',
                        '掌握生成多模态内容、构建个性化语音助手等能力'
                    ]
                },
                {
                    title: '构建更复杂的 AI 应用',
                    points: [
                        '动手实践阿里发布的 AI 技术解决方案系列，体验多模态交互技术',
                        '了解 AI 在医疗、教育、娱乐等行业的实际应用'
                    ]
                }
            ]
        },
        {
            id: 'prod', name: '生产环境应用实践', pct: 16, chs: ['6', '7', '8'],
            groups: [
                {
                    title: '内容安全合规检查手段',
                    points: [
                        '了解大模型开发中存在的内容安全问题',
                        '了解内容安全合规检测类型及常用方案'
                    ]
                },
                {
                    title: '大模型应用部署（云服务）安全',
                    points: [
                        '了解在云服务环境下应用系统安全的基本要素和解决方案'
                    ]
                },
                {
                    title: '在云上部署微调模型的基本方案',
                    points: [
                        '掌握如何使用 vLLM 进行大模型的部署操作',
                        '在云服务如（ECS、FC、PAI）中部署模型',
                        '在百炼上部署模型',
                        '了解如何利用云服务如函数计算（FC）实现 AI 助手的快速发布'
                    ]
                }
            ]
        }
    ],

    DATA_READY: false,
    CHAPTERS: {},
    CHAPTER_QUESTIONS: {},

    BANK: [],
    BY_CH: {},
    ID_MAP: {},
    CH_IDS: [],
    TOTAL: 0,

    STORE_KEY: 'acp_v2_store',

    state: {
        ui: {
            view: 'dashboard',
            ch: null,
            filter: 'all',
            mode: 'single',
            shuffle: false,
            pool: [],
            idx: 0,
            customTitle: null
        },
        session: {},
        exam: null,
        store: null,
        sel: new Set(),
        judged: false,
        listJudged: {},
        searchTimer: null,
        searchHits: [],
        toastTimer: null
    }
};