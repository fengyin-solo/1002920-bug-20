<template>
  <section class="page" data-module="training">
    <header class="page-head">
      <div>
        <h2>培训考核管理</h2>
        <p class="page-desc">勾选同一批人员成批送审考核结果；逐条带出培训内容与考核方式，不通过单独退回并写明原因。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openBatch()">成批送审考核</button>
        <button class="btn" type="button" @click="exportRows">导出培训考核清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>培训编号</span>
        <input v-model="filters.keyword" placeholder="按培训编号检索" />
      </label>
      <label class="filter-item">
        <span>培训状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '考核结果'" :class="resultClass(row)">{{ row[column] ?? '—' }}</span>
            <span v-else-if="column === '培训状态'">
              <span :class="['status-tag', statusClass(row.status)]">{{ row.status }}</span>
            </span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button v-if="row.status === '待培训'" class="link" type="button" @click="runAction('组织培训', row)">组织培训</button>
            <button v-if="row.status === '考核退回'" class="link" type="button" @click="openBatch(row)">重新送审</button>
            <button v-if="row.status === '已考核'" class="link" type="button" @click="runAction('归档', row)">归档</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的培训考核记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条，当前第 {{ page }} 页 / 共 {{ totalPages }} 页（每页 {{ size }} 条）</span>
      <span class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <button class="btn" type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 成批送审：一批人当成一件事 -->
    <div v-if="batchVisible" class="modal-mask" @click.self="batchVisible = false">
      <div class="modal wide">
        <div class="modal-head">
          <h3>成批送审考核结果</h3>
          <button class="link" type="button" @click="batchVisible = false">关闭</button>
        </div>

        <form class="filter-bar" @submit.prevent="loadCandidates">
          <label class="filter-item">
            <span>培训内容</span>
            <input v-model="candidateFilters.content" placeholder="按培训内容过滤" />
          </label>
          <label class="filter-item">
            <span>人员</span>
            <input v-model="candidateFilters.keyword" placeholder="编号 / 姓名 / 培训编号" />
          </label>
          <button class="btn" type="submit">带出名单</button>
        </form>

        <p class="modal-tip">
          待考核 {{ candidateTotal }} 人；已考核人员不再出现在名单中。勾选本批人员后逐条确认考核结果，
          不通过必须填写退回原因。
        </p>

        <div class="batch-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th class="col-check">
                  <input
                    type="checkbox"
                    :checked="allOnPageSelected"
                    @change="toggleAllOnPage"
                  />
                </th>
                <th>人员编号</th>
                <th>姓名</th>
                <th>培训编号</th>
                <th>培训内容</th>
                <th>考核方式</th>
                <th>考核结果</th>
                <th>退回原因（不通过时必填）</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="cand in candidates" :key="String(cand.id)" :class="{ selected: isSelected(cand.id) }">
                <td>
                  <input type="checkbox" :checked="isSelected(cand.id)" @change="toggleOne(cand)" />
                </td>
                <td>{{ cand['人员编号'] }}</td>
                <td>{{ cand['姓名'] }}</td>
                <td>{{ cand['培训编号'] }}</td>
                <td>{{ cand['培训内容'] }}</td>
                <td>
                  <template v-if="cand['考核方式']">{{ cand['考核方式'] }}</template>
                  <button v-else class="link warn" type="button" @click="retryMethod(cand)">
                    未取到，点此重发
                  </button>
                </td>
                <td>
                  <select v-model="formOf(cand).result">
                    <option value="通过">通过</option>
                    <option value="不通过">不通过</option>
                  </select>
                </td>
                <td>
                  <input
                    v-model="formOf(cand).reason"
                    :disabled="formOf(cand).result !== '不通过'"
                    :placeholder="formOf(cand).result === '不通过' ? '请写明不通过原因' : '仅不通过时填写'"
                  />
                </td>
              </tr>
              <tr v-if="!candidates.length">
                <td colspan="8" class="empty-state">没有可排入本批的人员（已考核人员不再出现）</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="batchError" class="error-text batch-error">{{ batchError }}</div>

        <div class="modal-foot">
          <span>已勾选 {{ selected.length }} 人</span>
          <span class="spacer" />
          <button class="btn" type="button" @click="batchVisible = false">取消</button>
          <button class="btn primary" type="button" :disabled="submitting" @click="submitBatch">
            {{ submitting ? '送审中…' : '整批提交' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 批次结果 / 批次详情 -->
    <div v-if="resultVisible" class="modal-mask" @click.self="resultVisible = false">
      <div class="modal wide">
        <div class="modal-head">
          <h3>批次处理结果 {{ batchResult?.batch_no }}</h3>
          <button class="link" type="button" @click="resultVisible = false">关闭</button>
        </div>
        <p class="modal-tip" v-if="batchResult">{{ batchResult.message }}</p>
        <div v-if="batchResult" class="stat-row batch-summary">
          <article class="stat-card"><span class="stat-label">本批条数</span><strong class="stat-value">{{ batchResult.total }}</strong></article>
          <article class="stat-card"><span class="stat-label">通过落记录</span><strong class="stat-value ok">{{ batchResult.passed }}</strong></article>
          <article class="stat-card"><span class="stat-label">单独退回</span><strong class="stat-value fail">{{ batchResult.rejected }}</strong></article>
          <article class="stat-card"><span class="stat-label">重复跳过</span><strong class="stat-value mute">{{ batchResult.skipped }}</strong></article>
          <article class="stat-card"><span class="stat-label">考核方式暂挂</span><strong class="stat-value warn">{{ batchResult.pending }}</strong></article>
        </div>
        <div class="batch-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>人员编号</th><th>培训编号</th><th>培训内容</th>
                <th>考核结果</th><th>处理状态</th><th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, idx) in batchResult?.items ?? []" :key="idx">
                <td>{{ item['人员编号'] ?? '—' }}</td>
                <td>{{ item['培训编号'] ?? '—' }}</td>
                <td>{{ item['培训内容'] ?? '—' }}</td>
                <td>{{ item['考核结果'] }}</td>
                <td><span :class="['status-tag', outcomeClass(String(item['状态'] ?? ''))]">{{ outcomeText(String(item['状态'] ?? '')) }}</span></td>
                <td>{{ item['说明'] }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="modal-foot">
          <span class="spacer" />
          <button class="btn primary" type="button" @click="afterBatchClose">知道了，返回列表</button>
        </div>
      </div>
    </div>

    <!-- 单条详情：失败原因留在这一页 -->
    <div v-if="detailVisible" class="modal-mask" @click.self="detailVisible = false">
      <div class="modal">
        <div class="modal-head">
          <h3>培训记录详情</h3>
          <button class="link" type="button" @click="detailVisible = false">关闭</button>
        </div>
        <table class="detail-table" v-if="detail">
          <tbody>
            <tr v-for="field in detailFields" :key="field">
              <th>{{ field }}</th>
              <td :class="{ 'error-text': field === '考核方式失败原因' }">{{ detail[field] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-foot">
          <span class="spacer" />
          <button class="btn" type="button" @click="detailVisible = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type BatchResultRow = Record<string, string | number | null>
type BatchSummary = {
  batch_no: string
  total: number
  passed: number
  rejected: number
  skipped: number
  pending: number
  message: string
  items: BatchResultRow[]
}

const ENDPOINT = '/api/training'
const columns = ['培训编号', '人员编号', '姓名', '培训内容', '培训日期', '培训讲师', '考核方式', '考核结果', '培训状态', '退回原因']
const statuses = ['待培训', '培训中', '考核退回', '已考核', '已归档']

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(10)
const errorMessage = ref('')
const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })
const stats = ref<Record<string, number>>({})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))
const statCards = computed(() => [
  { label: '待考核人数', value: stats.value['待考核'] ?? 0 },
  { label: '已考核人数', value: stats.value['已考核'] ?? 0 },
  { label: '考核退回', value: stats.value['考核退回'] ?? 0 },
  { label: '合格率', value: `${stats.value['合格率'] ?? 0}%` },
])

// ---------- 列表 ----------

function buildQuery(): string {
  const params = new URLSearchParams()
  if (filters.keyword.trim()) params.set('keyword', filters.keyword.trim())
  if (filters.status) params.set('status', filters.status)
  params.set('page', String(page.value))
  params.set('size', String(size.value))
  return params.toString()
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
    if (!response.ok) throw new Error('培训记录列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
    page.value = payload.page ?? page.value
    size.value = payload.size ?? size.value
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '培训考核列表读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) stats.value = await response.json()
  } catch {
    // 统计读不到不阻塞列表
  }
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  page.value = 1
  void reload()
}

function goPage(target: number) {
  if (target < 1 || target > totalPages.value) return
  page.value = target
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.detail ?? payload?.message ?? '培训考核动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '培训考核操作失败'
  }
}

// ---------- 详情（失败原因留在详情页） ----------

const detailVisible = ref(false)
const detail = ref<Row | null>(null)
const detailFields = [
  '培训编号', '人员编号', '姓名', '培训内容', '培训对象', '培训日期', '培训讲师',
  '考核方式', '考核方式失败原因', '考核结果', '培训状态', '退回原因', '批次号',
]

async function openDetail(row: Row) {
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error('详情读取失败')
    detail.value = await response.json()
    detailVisible.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '详情读取失败'
  }
}

// ---------- 成批送审 ----------

const batchVisible = ref(false)
const batchError = ref('')
const submitting = ref(false)
const candidates = ref<Row[]>([])
const candidateTotal = ref(0)
const candidateFilters = reactive({ content: '', keyword: '' })
// 勾选的每一行都独立带一份考核结果与退回原因，逐条处理互不影响。
const selectedMap = reactive<Record<number, { row: Row; result: string; reason: string }>>({})

const selected = computed(() => Object.values(selectedMap))
const allOnPageSelected = computed(() =>
  candidates.value.length > 0 && candidates.value.every((c) => isSelected(Number(c.id))))

function formOf(cand: Row) {
  const id = Number(cand.id)
  if (!selectedMap[id]) {
    selectedMap[id] = { row: cand, result: '通过', reason: '' }
  }
  return selectedMap[id]
}

function isSelected(id: string | number | null | undefined): boolean {
  return Boolean(selectedMap[Number(id)])
}

function toggleOne(cand: Row) {
  const id = Number(cand.id)
  if (selectedMap[id]) delete selectedMap[id]
  else formOf(cand)
}

function toggleAllOnPage(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  for (const cand of candidates.value) {
    const id = Number(cand.id)
    if (checked) formOf(cand)
    else delete selectedMap[id]
  }
}

async function loadCandidates() {
  batchError.value = ''
  const params = new URLSearchParams({ page: '1', size: '200' })
  if (candidateFilters.content.trim()) params.set('content', candidateFilters.content.trim())
  if (candidateFilters.keyword.trim()) params.set('keyword', candidateFilters.keyword.trim())
  try {
    const response = await request(`${ENDPOINT}/candidates?${params.toString()}`)
    if (!response.ok) throw new Error('待考核名单读取失败')
    const payload = await response.json()
    candidates.value = payload.items ?? []
    candidateTotal.value = payload.total ?? 0
  } catch (error) {
    batchError.value = error instanceof Error ? error.message : '待考核名单读取失败'
  }
}

function openBatch(prefill?: Row) {
  batchVisible.value = true
  batchError.value = ''
  candidateFilters.content = prefill ? String(prefill['培训内容'] ?? '') : ''
  candidateFilters.keyword = prefill ? String(prefill['人员编号'] ?? '') : ''
  void loadCandidates().then(() => {
    if (prefill) formOf(prefill)
  })
}

// 考核方式取不到时单条重发；成功回填名单与记录，失败原因留在详情页。
async function retryMethod(cand: Row) {
  batchError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${cand.id}/exam-method/retry`, { method: 'POST' })
    const payload = await response.json().catch(() => null)
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message ?? '考核方式重发失败，请稍后再试')
    }
    cand['考核方式'] = payload.entry['考核方式']
  } catch (error) {
    batchError.value = error instanceof Error ? error.message : '考核方式重发失败'
  }
}

async function submitBatch() {
  batchError.value = ''
  const chosen = selected.value
  if (!chosen.length) {
    batchError.value = '请先勾选本批要送审的人员'
    return
  }
  const missingReason = chosen.find((c) => c.result === '不通过' && !c.reason.trim())
  if (missingReason) {
    batchError.value = `${missingReason.row['姓名']} 考核不通过但未填写退回原因，请补填后再整批提交`
    return
  }
  submitting.value = true
  try {
    const items = chosen.map((c) => ({
      entry_id: Number(c.row.id),
      人员编号: String(c.row['人员编号'] ?? ''),
      培训内容: String(c.row['培训内容'] ?? ''),
      考核结果: c.result,
      退回原因: c.result === '不通过' ? c.reason.trim() : null,
    }))
    const response = await request(`${ENDPOINT}/batch-assess`, {
      method: 'POST',
      body: JSON.stringify({ items }),
    })
    if (!response.ok) {
      const detail = await response.json().catch(() => null)
      throw new Error(detail?.detail ?? '整批送审未被受理')
    }
    batchResult.value = (await response.json()) as BatchSummary
    batchVisible.value = false
    resultVisible.value = true
  } catch (error) {
    batchError.value = error instanceof Error ? error.message : '整批送审失败'
  } finally {
    submitting.value = false
  }
}

// ---------- 批次结果 ----------

const resultVisible = ref(false)
const batchResult = ref<BatchSummary | null>(null)

const outcomeTextMap: Record<string, string> = {
  passed: '通过落记录',
  rejected: '单独退回',
  skipped: '重复跳过',
  pending: '暂挂待重发',
}
const outcomeClassMap: Record<string, string> = {
  passed: 'st-ok',
  rejected: 'st-fail',
  skipped: 'st-mute',
  pending: 'st-warn',
}
function outcomeText(status: string) {
  return outcomeTextMap[status] ?? status
}
function outcomeClass(status: string) {
  return outcomeClassMap[status] ?? ''
}

async function afterBatchClose() {
  resultVisible.value = false
  batchResult.value = null
  Object.keys(selectedMap).forEach((key) => delete selectedMap[Number(key)])
  await Promise.all([reload(), loadStats(), loadCandidates()])
}

// ---------- 展示样式 ----------

function resultClass(row: Row) {
  if (row['考核结果'] === '通过') return 'result-ok'
  if (row['考核结果'] === '不通过') return 'result-fail'
  return ''
}

function statusClass(status: string | number | null | undefined) {
  if (status === '已考核') return 'st-ok'
  if (status === '考核退回') return 'st-fail'
  if (status === '培训中') return 'st-warn'
  if (status === '已归档') return 'st-mute'
  return ''
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
