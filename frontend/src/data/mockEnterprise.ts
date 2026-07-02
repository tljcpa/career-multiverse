/**
 * 企业端演示视图的 mock 数据。
 *
 * 这一页体现产品的第二个视角："企业也能在虚拟人才市场里做实验"。
 * 候选人有"数字分身 + 平行宇宙"，企业侧对应"企业数字分身 + 策略实验"。
 *
 * 所有数据写死在这里，Enterprise.vue 在 onMounted 里 import 加载，不调后端。
 * 数值经过手工调校，让"招潜力型培养"在 3 年维度上呈现可信的反转优势，
 * 用来支撑核心卖点：短视的高门槛策略在长期未必划算。
 */

// 单个企业的数字分身
export interface EnterpriseTwin {
  id: string
  codeName: string // 代号（脱敏）
  industry: string
  scale: string // 规模
  hiringBar: number // 招聘门槛（对齐候选人综合分 0-120 尺度）
  openRoles: RoleDemand[]
  cultureTags: string[]
  screeningStrategy: string // 当前筛选策略描述
  // 反向品牌视图用
  brandImpression: string // 应届生眼里的一句话印象
  attractsProfile: string // 能吸引到的候选人画像
}

export interface RoleDemand {
  role: string
  headcount: number
  urgency: 'high' | 'mid' | 'low' // 紧急度
}

// 策略实验：两种招聘策略 3 年后的对比维度
export interface StrategyOutcome {
  // 四个核心指标，均为 0-100 标准化分（越高越好）
  talentQuality: number // 人才质量分
  retentionRate: number // 留存率（%）
  laborCostScore: number // 人力成本得分（高=成本控制得好）
  teamStability: number // 团队稳定性
}

export interface StrategyExperiment {
  strategyA: {
    name: string
    subtitle: string
    outcome: StrategyOutcome
    yearByYear: { year: string; talentQuality: number; cost: number }[] // 逐年趋势（cost 为相对人力成本指数）
  }
  strategyB: {
    name: string
    subtitle: string
    outcome: StrategyOutcome
    yearByYear: { year: string; talentQuality: number; cost: number }[]
  }
  verdict: string // 实验结论
}

// hiring_bar 在市场里的相对位置（反向品牌视图用）
export interface MarketPosition {
  myBar: number
  marketMedian: number
  marketTop10: number // 市场前 10% 门槛线
  percentile: number // 我的门槛在市场里的分位（0-100）
  desc: string
}

// ============ 数据 ============

export const enterprises: EnterpriseTwin[] = [
  {
    id: 'yanhuo',
    codeName: '焰火科技',
    industry: '互联网 / 大模型应用',
    scale: '500-1000 人 · C 轮',
    hiringBar: 82,
    openRoles: [
      { role: '大模型算法工程师', headcount: 12, urgency: 'high' },
      { role: '前端工程师', headcount: 8, urgency: 'mid' },
      { role: '产品经理（AI 方向）', headcount: 4, urgency: 'high' }
    ],
    cultureTags: ['快速迭代', '扁平化', '结果导向', '高强度'],
    screeningStrategy: '硬门槛优先：学历 985/211 + 大厂实习，简历初筛卡得很紧',
    brandImpression: '光鲜、卷、给得起，但进去容易被榨干',
    attractsProfile: '名校背景、履历漂亮、追求短期高薪的头部候选人'
  },
  {
    id: 'xingyu-1',
    codeName: '星域-1',
    industry: '智能制造 / 工业软件',
    scale: '2000+ 人 · 已上市',
    hiringBar: 68,
    openRoles: [
      { role: '嵌入式软件工程师', headcount: 20, urgency: 'high' },
      { role: '机械结构工程师', headcount: 15, urgency: 'mid' },
      { role: '测试工程师', headcount: 10, urgency: 'low' }
    ],
    cultureTags: ['稳健', '师徒制', '长期主义', '工程师文化'],
    screeningStrategy: '潜力优先：看基础扎实度 + 学习曲线，愿意招双非里的好苗子培养',
    brandImpression: '不算大厂但稳，能学到真东西，师傅带得细',
    attractsProfile: '基础扎实、看重成长、想沉淀技术的务实型候选人'
  },
  {
    id: 'siyuan',
    codeName: '思源智行',
    industry: '自动驾驶 / 出行',
    scale: '800-1200 人 · D 轮',
    hiringBar: 75,
    openRoles: [
      { role: '感知算法工程师', headcount: 10, urgency: 'high' },
      { role: '规控工程师', headcount: 6, urgency: 'high' },
      { role: '数据平台工程师', headcount: 5, urgency: 'mid' }
    ],
    cultureTags: ['技术驱动', '容错试错', '扁平', '使命感'],
    screeningStrategy: '混合策略：核心岗卡门槛，储备岗招潜力，两条通道并行',
    brandImpression: '技术氛围浓、赛道性感，但商业化压力肉眼可见',
    attractsProfile: '有真本事、认可赛道、愿意赌一把的技术理想主义者'
  }
]

// 策略实验数据：每家企业一套（key 为 enterprise id）
// 设计意图：让"招潜力型培养"在人才质量与稳定性上于第 3 年反超，
// 但在人力成本得分上短期不占优（培养有投入），呈现真实的 trade-off。
export const strategyExperiments: Record<string, StrategyExperiment> = {
  yanhuo: {
    strategyA: {
      name: '只招高学历',
      subtitle: '硬门槛卡死，只要名校 + 大厂履历',
      outcome: {
        talentQuality: 78,
        retentionRate: 61,
        laborCostScore: 48,
        teamStability: 55
      },
      yearByYear: [
        { year: '第 1 年', talentQuality: 80, cost: 100 },
        { year: '第 2 年', talentQuality: 76, cost: 108 },
        { year: '第 3 年', talentQuality: 72, cost: 118 }
      ]
    },
    strategyB: {
      name: '招潜力型培养',
      subtitle: '放宽学历门槛，看学习曲线 + 内部培养',
      outcome: {
        talentQuality: 84,
        retentionRate: 83,
        laborCostScore: 72,
        teamStability: 86
      },
      yearByYear: [
        { year: '第 1 年', talentQuality: 62, cost: 74 },
        { year: '第 2 年', talentQuality: 78, cost: 82 },
        { year: '第 3 年', talentQuality: 88, cost: 90 }
      ]
    },
    verdict:
      '第 1 年高学历组领先，但高薪挖来的人流动快、成本逐年抬升；潜力组第 2 年追平、第 3 年在质量与稳定性上全面反超，综合人力成本反而更低。对焰火这种高强度环境，"招得贵不如留得住"。'
  },
  'xingyu-1': {
    strategyA: {
      name: '只招高学历',
      subtitle: '硬门槛卡死，只要名校 + 大厂履历',
      outcome: {
        talentQuality: 70,
        retentionRate: 52,
        laborCostScore: 40,
        teamStability: 48
      },
      yearByYear: [
        { year: '第 1 年', talentQuality: 74, cost: 100 },
        { year: '第 2 年', talentQuality: 68, cost: 112 },
        { year: '第 3 年', talentQuality: 63, cost: 124 }
      ]
    },
    strategyB: {
      name: '招潜力型培养',
      subtitle: '放宽学历门槛，看基础扎实度 + 师徒制培养',
      outcome: {
        talentQuality: 82,
        retentionRate: 88,
        laborCostScore: 80,
        teamStability: 90
      },
      yearByYear: [
        { year: '第 1 年', talentQuality: 58, cost: 66 },
        { year: '第 2 年', talentQuality: 76, cost: 72 },
        { year: '第 3 年', talentQuality: 89, cost: 78 }
      ]
    },
    verdict:
      '制造业岗位对稳定性极敏感，名校生把星域当跳板、留存率腰斩；潜力组经师徒制沉淀后质量最高、几乎不走人。这里"潜力型培养"是压倒性最优解。'
  },
  siyuan: {
    strategyA: {
      name: '只招高学历',
      subtitle: '硬门槛卡死，只要名校 + 大厂履历',
      outcome: {
        talentQuality: 83,
        retentionRate: 66,
        laborCostScore: 52,
        teamStability: 60
      },
      yearByYear: [
        { year: '第 1 年', talentQuality: 85, cost: 100 },
        { year: '第 2 年', talentQuality: 82, cost: 106 },
        { year: '第 3 年', talentQuality: 79, cost: 114 }
      ]
    },
    strategyB: {
      name: '招潜力型培养',
      subtitle: '放宽学历门槛，看真实工程能力 + 试错空间',
      outcome: {
        talentQuality: 85,
        retentionRate: 79,
        laborCostScore: 70,
        teamStability: 82
      },
      yearByYear: [
        { year: '第 1 年', talentQuality: 68, cost: 78 },
        { year: '第 2 年', talentQuality: 80, cost: 85 },
        { year: '第 3 年', talentQuality: 90, cost: 92 }
      ]
    },
    verdict:
      '自动驾驶核心算法岗高学历仍有先发优势，但差距在 3 年内被抹平且稳定性更差。思源现行"混合策略"是理性的：核心岗守门槛、储备岗放潜力，两条通道对冲风险。'
  }
}

// 反向品牌：每家企业在市场里的门槛相对位置
export const marketPositions: Record<string, MarketPosition> = {
  yanhuo: {
    myBar: 82,
    marketMedian: 64,
    marketTop10: 88,
    percentile: 84,
    desc: '你的招聘门槛处于市场前 16%，接近头部大厂。这意味着候选人会拿你和字节、阿里同台比较——薪资与成长空间需要撑得起这个门槛，否则名校生只是把你当保底。'
  },
  'xingyu-1': {
    myBar: 68,
    marketMedian: 64,
    marketTop10: 88,
    percentile: 58,
    desc: '你的门槛略高于市场中位，属于"够得着但不吓人"的舒适区。对务实型候选人友好，但要主动讲清"能学到什么"，否则容易在名气战里被互联网公司盖过。'
  },
  siyuan: {
    myBar: 75,
    marketMedian: 64,
    marketTop10: 88,
    percentile: 72,
    desc: '你的门槛处于市场前 28%，赛道光环能吸引理想主义者，但商业化不确定性是候选人最大顾虑。品牌叙事应从"性感赛道"转向"这里能证明你自己"。'
  }
}
