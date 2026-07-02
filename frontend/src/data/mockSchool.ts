/**
 * 学校端（高校就业指导中心）演示视图的 mock 数据。
 *
 * 产品商业主战场：高校就业中心购买"本校学生群体的人才洞察"。
 * C 端学生个人跑 sim 是流量入口，B 端高校买群体聚合报告才是营收。
 *
 * 这里全部写死，不调后端。示例院校："北岭理工大学"（虚构，避免影射真实学校）。
 * 数字口径统一：五维分 0-100；市场均值来自沙盘全体求职者聚合（也写死）。
 */

// ========= 示例院校元信息 =========

export interface SchoolMeta {
  school_name: string
  cohort_label: string // 届别
  student_count: number // 纳入洞察的学生数
  simulated_universes: number // 每个学生跑的平行宇宙数
  updated_at: string
}

export const schoolMeta: SchoolMeta = {
  school_name: '北岭理工大学',
  cohort_label: '2026 届',
  student_count: 1280,
  simulated_universes: 1000,
  updated_at: '2026-06-30'
}

// ========= 1. 本校群体五维竞争力分布 =========

/**
 * 五维：项目 / 实习 / 成就 / 沟通 / GPA。
 * mean = 本校群体均值；p25 / p75 = 群体分位，用来画分布带；market = 全市场均值对照。
 */
export interface DimStat {
  key: string
  label: string
  mean: number
  p25: number
  p75: number
  market: number // 全市场均值
}

export const dimStats: DimStat[] = [
  { key: 'project', label: '项目含金量', mean: 68, p25: 52, p75: 82, market: 61 },
  { key: 'internship', label: '实习含金量', mean: 49, p25: 33, p75: 66, market: 58 },
  { key: 'achievement', label: '成就/竞赛/开源', mean: 71, p25: 55, p75: 86, market: 55 },
  { key: 'communication', label: '沟通表达', mean: 57, p25: 46, p75: 68, market: 63 },
  { key: 'gpa', label: '专业 GPA 分位', mean: 64, p25: 50, p75: 78, market: 56 }
]

// ========= 2. 技能缺口分析（本校均值 - 市场均值）=========

/**
 * gap < 0 表示本校群体在该维度弱于市场，是重点补强方向。
 * 直接从 dimStats 派生也可以，但为了页面清晰单独给出带解读的结构。
 */
export interface SkillGap {
  key: string
  label: string
  school: number
  market: number
  gap: number // school - market，负数为短板
  advice: string
}

export const skillGaps: SkillGap[] = dimStats
  .map((d) => {
    const gap = d.mean - d.market
    let advice = ''
    if (d.key === 'internship') {
      advice = '本校学生实习覆盖率偏低，建议前置校企实习对接、增设大三暑期实习学分。'
    } else if (d.key === 'communication') {
      advice = '沟通表达弱于市场，建议开设模拟面试、简历量化表达工作坊。'
    } else if (d.key === 'project') {
      advice = '项目略强于市场，可继续放大：推动项目成果开源、参与产业级课题。'
    } else if (d.key === 'achievement') {
      advice = '竞赛与开源是本校强项，建议以此为招聘亮点重点包装。'
    } else {
      advice = 'GPA 分位高于市场，学业基础扎实，可主打研发/研究型岗位。'
    }
    return {
      key: d.key,
      label: d.label,
      school: d.mean,
      market: d.market,
      gap,
      advice
    }
  })
  .sort((a, b) => a.gap - b.gap) // 短板在前

// ========= 3. 该重点对接的 Top 雇主 =========

/**
 * 按"本校学生群体画像与该雇主招聘偏好的匹配度"排序。
 * match = 匹配度 0-100；expected_offers = 1000 次模拟里该雇主给出的期望 offer 数（群体口径）。
 * 公司用代号（焰火 / 星域-1 / 思源智行 / 蓝盾云 等），不指向真实公司。
 */
export interface EmployerMatch {
  code_name: string
  industry: string
  match: number
  hiring_bar: number
  expected_offers: number
  reason: string
}

export const topEmployers: EmployerMatch[] = [
  {
    code_name: '思源智行',
    industry: '自动驾驶',
    match: 91,
    hiring_bar: 74,
    expected_offers: 186,
    reason: '重视竞赛与开源背景，与本校成就维度强项高度契合。'
  },
  {
    code_name: '焰火',
    industry: '互联网-短视频',
    match: 87,
    hiring_bar: 82,
    expected_offers: 142,
    reason: '算法岗看重项目深度，本校项目含金量高于市场。'
  },
  {
    code_name: '蓝盾云',
    industry: '云计算-安全',
    match: 84,
    hiring_bar: 70,
    expected_offers: 168,
    reason: '门槛适中，对 GPA 与工程能力并重，匹配本校学业基础。'
  },
  {
    code_name: '星域-1',
    industry: '航天-卫星',
    match: 82,
    hiring_bar: 78,
    expected_offers: 95,
    reason: '偏好扎实理论功底，本校 GPA 分位高于市场均值。'
  },
  {
    code_name: '磐石银行科技',
    industry: '金融科技',
    match: 76,
    hiring_bar: 68,
    expected_offers: 121,
    reason: '稳态岗位多、门槛友好，适合保底批量对接。'
  },
  {
    code_name: '晨曦医疗智能',
    industry: '医疗 AI',
    match: 73,
    hiring_bar: 72,
    expected_offers: 88,
    reason: '交叉学科需求，本校跨专业项目学生匹配度较高。'
  }
]

// ========= 4. 群体就业去向预测 =========

/**
 * 1000 次模拟聚合到群体后的最可能去向分布（占比之和≈100）。
 * median_salary 单位：元/月（应届口径）。
 */
export interface DestinationSlice {
  name: string
  ratio: number // 占比 %
  median_salary: number // 中位月薪
}

export const destinations: DestinationSlice[] = [
  { name: '互联网/软件', ratio: 31, median_salary: 16500 },
  { name: '硬科技/智能制造', ratio: 22, median_salary: 14200 },
  { name: '金融科技', ratio: 13, median_salary: 15800 },
  { name: '国企/研究院', ratio: 12, median_salary: 11000 },
  { name: '升学/读研', ratio: 11, median_salary: 0 },
  { name: '医疗/生物 AI', ratio: 6, median_salary: 13500 },
  { name: '其他/待定', ratio: 5, median_salary: 9000 }
]

/**
 * 群体整体的中位起薪与就业率，供顶部 KPI 用。
 */
export const cohortOutcome = {
  overall_median_salary: 14800, // 元/月，剔除升学后
  employment_rate: 0.89, // 有 offer 比例（模拟口径）
  multi_offer_rate: 0.41, // 拿到 ≥2 offer 比例
  top_tier_offer_rate: 0.27 // 拿到高门槛(bar≥80)雇主 offer 比例
}
