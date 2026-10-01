<template>
  <section class="page" data-module="training">
    <header class="page-head">
      <div>
        <h2>培训考核管理</h2>
        <p class="page-desc">勾选同一批人员成批提交考核结果：逐条带出培训内容与考核方式，不通过的单独退回并写明原因，已考核的不再重复排进下一批。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openBatch">批量提交考核（已选 {{ selectedIds.length }} 人）</button>
        <button class="btn" type="button" @click="openCreate">登记培训记录</button>
        <button class="btn" type="button" @click="exportRows">导出培训考核清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>培训编号 / 培训对象</span>
        <input v-model="keyword" placeholder="按编号或姓名检索" />
      </label>
      <label class="filter-item">
        <span>培训状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">
            <input type="checkbox" :checked="allSelectableChecked" title="勾选本页全部可考核人员" @change="toggleAll" />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>培训状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input
              type="checkbox"
              :checked="selectedIds.includes(Number(row.id))"
              :disabled="!isSelectable(row)"
              :title="isSelectable(row) ? '勾选加入本批考核' : '已考核，不会重复排进下一批'"
              @change="toggleRow(row)"
            />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] || '—' }}</td>
          <td><span class="badge" :class="statusClass(row.status)">{{ row.status || '—' }}</span></td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 3" class="empty-state">暂无培训考核数据，可调整筛选条件或先登记培训记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>本页 {{ rows.length }} 条 / 共 {{ total }} 条培训考核记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span class="pager">
        <button class="btn ghost" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <span>第 {{ page }} / {{ pageCount }} 页</span>
        <button class="btn ghost" type="button" :disabled="page >= pageCount" @click="goPage(page + 1)">下一页</button>
      </span>
    </footer>

    <div v-if="batchVisible" class="modal-mask" @click.self="closeBatch">
      <div class="modal-panel wide">
        <header class="modal-head">
          <h3>批量提交考核结果</h3>
          <button class="link" type="button" @click="closeBatch">关闭</button>
        </header>

        <p v-if="batchLoading" class="modal-tip">正在逐条带出培训内容与考核方式…</p>
        <div v-else-if="batchLoadError" class="modal-tip">
          <span class="error-text">{{ batchLoadError }}</span>
          <button class="btn" type="button" @click="loadContext">重发</button>
        </div>

        <template v-else>
          <table class="data-table batch-table">
            <thead>
              <tr>
                <th>培训编号</th>
                <th>培训对象</th>
                <th>培训内容</th>
                <th>考核方式</th>
                <th>考核结果</th>
                <th>退回原因</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in batchRows" :key="item.id" :class="{ 'row-disabled': !item.eligible }">
                <td>{{ item.培训编号 ?? item.id }}</td>
                <td>{{ item.培训对象 ?? '—' }}</td>
                <td>{{ item.培训内容 ?? '—' }}</td>
                <template v-if="item.eligible">
                  <td><input v-model="item.考核方式" placeholder="如：笔试 / 实操 / 口试" /></td>
                  <td>
                    <select v-model="item.考核结果">
                      <option value="">请选择</option>
                      <option value="通过">通过</option>
                      <option value="不通过">不通过</option>
                    </select>
                  </td>
                  <td>
                    <input
                      v-model="item.退回原因"
                      :class="{ 'input-required': item.考核结果 === '不通过' && !item.退回原因.trim() }"
                      :placeholder="item.考核结果 === '不通过' ? '必填：写明退回原因' : '不通过时填写'"
                    />
                  </td>
                </template>
                <td v-else colspan="3" class="muted">{{ item.note }}</td>
              </tr>
            </tbody>
          </table>

          <div v-if="receipts.length" class="receipt-box">
            <p class="receipt-summary" :class="batchOk ? 'ok-text' : 'error-text'">{{ batchMessage }}</p>
            <ul class="receipt-list">
              <li v-for="receipt in receipts" :key="String(receipt.entry_id)">
                <strong>{{ receipt.培训编号 ?? receipt.entry_id }} {{ receipt.培训对象 ?? '' }}</strong>
                <span class="badge" :class="receipt.ok ? 'badge-green' : 'badge-red'">{{ receipt.outcome }}</span>
                <span>{{ receipt.message }}</span>
              </li>
            </ul>
          </div>

          <footer class="modal-foot">
            <span class="muted">共 {{ batchRows.length }} 条，其中 {{ eligibleCount }} 条进入本批</span>
            <span class="row-actions">
              <button v-if="hasFailed" class="btn" type="button" :disabled="submitting" @click="resubmitFailed">仅重发待补正条目</button>
              <button class="btn primary" type="button" :disabled="submitting || !eligibleCount" @click="submitBatch(false)">
                {{ submitting ? '提交中…' : '提交本批考核' }}
              </button>
            </span>
          </footer>
        </template>
      </div>
    </div>

    <div v-if="detailEntry" class="modal-mask" @click.self="detailEntry = null">
      <div class="modal-panel">
        <header class="modal-head">
          <h3>培训记录详情</h3>
          <button class="link" type="button" @click="detailEntry = null">关闭</button>
        </header>
        <dl class="detail-list">
          <dt>当前状态</dt>
          <dd><span class="badge" :class="statusClass(detailEntry.status)">{{ detailEntry.status || '—' }}</span></dd>
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd :class="{ 'error-text': field === '退回原因' && detailEntry[field] }">{{ detailEntry[field] || '—' }}</dd>
          </template>
        </dl>
      </div>
    </div>

    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal-panel">
        <header class="modal-head">
          <h3>登记培训记录</h3>
          <button class="link" type="button" @click="createVisible = false">关闭</button>
        </header>
        <div class="form-grid">
          <label v-for="field in createFields" :key="field">
            <span>{{ field }}</span>
            <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
          </label>
        </div>
        <footer class="modal-foot">
          <span v-if="createError" class="error-text">{{ createError }}</span>
          <span v-else class="muted">培训编号、培训内容、培训对象为必填</span>
          <button class="btn primary" type="button" @click="submitCreate">保存登记</button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null | undefined>

interface BatchRow {
  id: number
  培训编号?: string
  培训对象?: string
  培训内容?: string
  考核方式: string
  考核结果: string
  退回原因: string
  eligible: boolean
  note: string
}

interface Receipt {
  entry_id: number | null
  培训编号: string | null
  培训对象: string | null
  ok: boolean
  outcome: string
  message: string
}

const ENDPOINT = '/api/training'
const columns = ['培训编号', '培训对象', '培训内容', '培训日期', '培训讲师', '考核方式', '考核结果']
const statuses = ['待培训', '培训中', '已退回', '已考核', '已归档']
const SETTLED = ['已考核', '已归档']
const detailFields = ['培训编号', '培训内容', '培训对象', '培训日期', '培训讲师', '考核方式', '考核结果', '考核日期', '退回原因']
const createFields = ['培训编号', '培训内容', '培训对象', '培训日期', '培训讲师', '考核方式']

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const size = 10
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')
const stats = ref<Record<string, number>>({})
const selectedIds = ref<number[]>([])

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / size)))
const statCards = computed(() => [
  { label: '待考核', value: stats.value['待考核'] ?? 0 },
  { label: '已考核', value: stats.value['已考核'] ?? 0 },
  { label: '已退回', value: stats.value['已退回'] ?? 0 },
  { label: '合格率', value: `${stats.value['合格率'] ?? 0}%` },
])

const selectableRows = computed(() => rows.value.filter(isSelectable))
const allSelectableChecked = computed(
  () => selectableRows.value.length > 0 && selectableRows.value.every((row) => selectedIds.value.includes(Number(row.id))),
)

function isSelectable(row: Row) {
  return !SETTLED.includes(String(row.status ?? ''))
}

function statusClass(status: unknown) {
  const value = String(status ?? '')
  if (value === '已考核') return 'badge-green'
  if (value === '已退回') return 'badge-red'
  if (value === '已归档') return 'badge-gray'
  return 'badge-blue'
}

function toggleRow(row: Row) {
  const id = Number(row.id)
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

function toggleAll() {
  const pageIds = selectableRows.value.map((row) => Number(row.id))
  selectedIds.value = allSelectableChecked.value
    ? selectedIds.value.filter((id) => !pageIds.includes(id))
    : [...new Set([...selectedIds.value, ...pageIds])]
}

function applyFilters() {
  page.value = 1
  void reload()
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  page.value = 1
  void reload()
}

function goPage(target: number) {
  if (target < 1 || target > pageCount.value) return
  page.value = target
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams({ page: String(page.value), size: String(size) })
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('培训记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
    if (!rows.value.length && page.value > 1) {
      page.value -= 1
      return reload()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '培训考核列表读取失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (response.ok) {
      stats.value = await response.json()
    }
  } catch {
    stats.value = {}
  }
}

const batchVisible = ref(false)
const batchLoading = ref(false)
const batchLoadError = ref('')
const batchRows = ref<BatchRow[]>([])
const receipts = ref<Receipt[]>([])
const batchMessage = ref('')
const batchOk = ref(true)
const submitting = ref(false)

const eligibleCount = computed(() => batchRows.value.filter((row) => row.eligible).length)
const hasFailed = computed(() => receipts.value.some((receipt) => !receipt.ok))

function openBatch() {
  if (!selectedIds.value.length) {
    errorMessage.value = '请先在列表勾选要参加本批考核的人员'
    return
  }
  errorMessage.value = ''
  batchVisible.value = true
  receipts.value = []
  batchMessage.value = ''
  void loadContext()
}

function closeBatch() {
  batchVisible.value = false
}

async function loadContext() {
  batchLoading.value = true
  batchLoadError.value = ''
  try {
    const response = await request(`${ENDPOINT}/assessment-context?ids=${selectedIds.value.join(',')}`)
    if (!response.ok) {
      throw new Error(`考核方式读取失败（接口返回 ${response.status}），可点击重发再试`)
    }
    const payload = await response.json()
    batchRows.value = (payload.items ?? []).map((item: Record<string, unknown>) => ({
      id: Number(item.id),
      培训编号: item.培训编号 as string | undefined,
      培训对象: item.培训对象 as string | undefined,
      培训内容: item.培训内容 as string | undefined,
      考核方式: String(item.考核方式 ?? ''),
      考核结果: '',
      退回原因: '',
      eligible: Boolean(item.eligible),
      note: String(item.note ?? ''),
    }))
  } catch (error) {
    batchLoadError.value = error instanceof Error ? error.message : '考核方式读取失败，可点击重发再试'
  } finally {
    batchLoading.value = false
  }
}

function buildItems(ids: number[]) {
  return batchRows.value
    .filter((row) => row.eligible && ids.includes(row.id))
    .map((row) => ({
      entry_id: row.id,
      考核结果: row.考核结果,
      考核方式: row.考核方式,
      退回原因: row.退回原因,
    }))
}

async function submitBatch(onlyFailed: boolean) {
  const ids = onlyFailed
    ? receipts.value.filter((receipt) => !receipt.ok).map((receipt) => Number(receipt.entry_id))
    : batchRows.value.filter((row) => row.eligible).map((row) => row.id)
  const items = buildItems(ids)
  if (!items.length) {
    batchOk.value = false
    batchMessage.value = '本批没有可提交的考核记录'
    return
  }
  submitting.value = true
  try {
    const response = await request(`${ENDPOINT}/assessments/batch`, {
      method: 'POST',
      body: JSON.stringify({ items }),
    })
    if (!response.ok) {
      throw new Error(`批量提交未受理（接口返回 ${response.status}），请稍后重试`)
    }
    const payload = await response.json()
    batchOk.value = Boolean(payload.ok)
    batchMessage.value = String(payload.message ?? '')
    mergeReceipts(payload.results ?? [])
    const settled = new Set(
      (payload.results ?? [])
        .filter((receipt: Receipt) => receipt.outcome === '已入档' || receipt.outcome === '已跳过')
        .map((receipt: Receipt) => Number(receipt.entry_id)),
    )
    selectedIds.value = selectedIds.value.filter((id) => !settled.has(id))
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    batchOk.value = false
    batchMessage.value = error instanceof Error ? error.message : '批量提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}

function resubmitFailed() {
  void submitBatch(true)
}

function mergeReceipts(incoming: Receipt[]) {
  const merged = new Map(receipts.value.map((receipt) => [Number(receipt.entry_id), receipt]))
  for (const receipt of incoming) {
    merged.set(Number(receipt.entry_id), receipt)
  }
  receipts.value = [...merged.values()]
}

const detailEntry = ref<Row | null>(null)

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('培训记录详情读取失败')
    }
    detailEntry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '培训记录详情读取失败'
  }
}

const createVisible = ref(false)
const createError = ref('')
const createForm = ref<Record<string, string>>({})

function openCreate() {
  createForm.value = Object.fromEntries(createFields.map((field) => [field, '']))
  createError.value = ''
  createVisible.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      createError.value = String(payload.message ?? '登记失败，请检查必填字段')
      return
    }
    createVisible.value = false
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '登记失败，请稍后重试'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
