/**
 * ghg-insight-builder: Pure Vanilla JavaScript Application
 * 프론트엔드 프레임워크(React, Vue 등) 배제, 순수 브라우저 API 및 Chart.js 사용
 */

const SECTOR_KO_MAP = {
    "Electricity and heat": "전기 및 열 생산 (발전소)",
    "Transport": "수송 (교통/차량/항공)",
    "Manufacturing and construction": "제조 및 건설업",
    "Agriculture": "농업",
    "Industry": "산업 공정",
    "Buildings": "건물 (냉난방)",
    "Waste": "폐기물",
    "Fugitive emissions": "탈루 배출 (에너지 채굴/누출)",
    "Land-use change and forestry": "산림 및 토지이용 (흡수원)",
    "Other fuel combustion": "기타 연료 연소",
    "Aviation and shipping": "국제 항공 및 해운",
    "Entity": "국가 / 개체명",
    "Code": "국가 코드",
    "Year": "연도"
};

function toKoName(name) {
    if (!name) return '';
    return SECTOR_KO_MAP[name] || name;
}

const appState = {
    serverReady: false,
    apiKeyConfigured: false,
    model: null,
    currentFile: null,
    inspectResult: null,
    suggestions: [],
    selectedSuggestion: null,
    runResult: null,
    lastExplanation: null,
    customVisData: null,
    debugLogs: []
};

let currentChartInstance = null;

// ==========================================================================
// 1. 규격 콘솔 및 디버그 로깅 헬퍼
// ==========================================================================
function addDebugLog(category, message, data = null) {
    const timestamp = new Date().toLocaleTimeString();
    const logLine = `[${timestamp}] ${category} ${message}`;
    console.log(logLine, data ? data : '');

    appState.debugLogs.push(logLine);
    if (appState.debugLogs.length > 50) appState.debugLogs.shift();

    const pre = document.getElementById('debug-status-pre');
    if (pre) {
        const stateSummary = {
            serverReady: appState.serverReady,
            apiKeyConfigured: appState.apiKeyConfigured,
            model: appState.model,
            currentFile: appState.currentFile ? `${appState.currentFile.name} (${appState.currentFile.size}B)` : null,
            hasInspectResult: !!appState.inspectResult,
            selectedTool: appState.selectedSuggestion ? appState.selectedSuggestion.tool : null,
            hasRunResult: !!appState.runResult,
            hasReport: !!appState.lastExplanation,
            recentLogs: appState.debugLogs.slice(-6)
        };
        pre.textContent = JSON.stringify(stateSummary, null, 2);
    }
}

// ==========================================================================
// 2. 초기화 및 서버 헬스체크
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
    addDebugLog('[PAGE]', '페이지 로드 완료');
    checkServerHealth();
    initEventListeners();
});

async function checkServerHealth() {
    const serverBadge = document.getElementById('server-status');
    const apiBadge = document.getElementById('api-key-status');

    try {
        const res = await fetch('/health');
        if (!res.ok) throw new Error(`서버 응답 오류 (HTTP ${res.status})`);
        const data = await res.json();

        appState.serverReady = (data.status === 'ok');
        appState.apiKeyConfigured = data.api_key_configured;
        appState.model = data.model;

        serverBadge.textContent = '서버: 정상 가동';
        serverBadge.className = 'badge badge-success';

        if (data.api_key_configured) {
            apiBadge.textContent = `Gemini 연결됨 (${data.model})`;
            apiBadge.className = 'badge badge-success';
        } else {
            apiBadge.textContent = 'API Key 미설정 (.env 확인)';
            apiBadge.className = 'badge badge-warning';
        }
        addDebugLog('[HEALTH]', `상태 확인 완료 (model=${data.model}, api_configured=${data.api_key_configured})`);
    } catch (err) {
        serverBadge.textContent = '서버 연결 실패';
        serverBadge.className = 'badge badge-error';
        apiBadge.textContent = '상태 확인 불가';
        apiBadge.className = 'badge badge-error';
        addDebugLog('[ERROR]', `서버 헬스체크 실패: ${err.message}`);
    }
}

// ==========================================================================
// 3. 이벤트 리스너 등록
// ==========================================================================
function initEventListeners() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');

    // 드래그 앤 드롭
    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    // 발표/데모 전용: 원클릭 샘플 데이터 로드
    const sampleBtn = document.getElementById('btn-load-sample');
    if (sampleBtn) {
        sampleBtn.addEventListener('click', handleLoadSample);
    }

    // 자연어 질문 전송 및 추천 칩 클릭
    document.getElementById('btn-ask-submit').addEventListener('click', handleUserAsk);
    document.getElementById('ask-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleUserAsk();
    });

    document.querySelectorAll('.chip-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const query = btn.getAttribute('data-query');
            document.getElementById('ask-input').value = query;
            handleUserAsk();
        });
    });

    // 맞춤 시각화 실행 버튼
    document.getElementById('btn-trigger-custom-run').addEventListener('click', () => {
        if (appState.customVisData) {
            runSelectedTool({
                tool: appState.customVisData.recommended_tool,
                params: appState.customVisData.params,
                reference_period: appState.customVisData.params?.reference_period || '2023',
                why: appState.customVisData.visualization_title || '자연어 질문 기반 맞춤 시각화'
            });
        }
    });

    // Step 2 추천 새로고침 버튼
    document.getElementById('btn-request-suggest').addEventListener('click', requestSuggestions);

    // Step 3 -> 4: 보고서 작성 요청 버튼
    document.getElementById('btn-request-explain').addEventListener('click', () => {
        const step4 = document.getElementById('step-4-section');
        step4.classList.remove('disabled-section');
        step4.scrollIntoView({ behavior: 'smooth' });
    });

    // Step 4: 보고서 생성 버튼
    document.getElementById('btn-generate-report').addEventListener('click', requestExplanation);

    // 보고서 복사 버튼
    document.getElementById('btn-copy-report').addEventListener('click', copyReportToClipboard);

    // 디버그 정보 복사 버튼
    document.getElementById('btn-copy-debug').addEventListener('click', copyDebugInfo);

    // 보고서 Q&A 챗봇 메시지 전송
    document.getElementById('btn-chat-send').addEventListener('click', handleChatSend);
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleChatSend();
    });

    // 챗봇 추천 질문 칩 클릭
    document.querySelectorAll('.chat-chip-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const chatMsg = btn.getAttribute('data-chat');
            document.getElementById('chat-input').value = chatMsg;
            handleChatSend();
        });
    });
}

// ==========================================================================
// 4. Step 1: 파일 업로드 및 진단 (/inspect)
// ==========================================================================
async function handleLoadSample() {
    addDebugLog('[SAMPLE]', '원클릭 공식 샘플 데이터 로드 시작');
    const sampleBtn = document.getElementById('btn-load-sample');
    const originalText = sampleBtn.innerHTML;
    sampleBtn.innerHTML = '⏳ 데이터셋 탑재 및 진단 중...';
    sampleBtn.disabled = true;

    try {
        const res = await fetch('/load-sample', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '샘플 데이터 로드 실패');

        appState.currentFile = { name: data.filename, size: data.file_size_bytes };
        appState.inspectResult = data;
        addDebugLog('[SAMPLE]', `샘플 로드 성공: rows=${data.rows}, cols=${data.columns}`);

        const inspectPanel = document.getElementById('inspect-result-panel');
        inspectPanel.classList.remove('hidden-panel');
        renderInspectResult(data);

        document.getElementById('ask-section').classList.remove('disabled-section');
        document.getElementById('step-2-section').classList.remove('disabled-section');

        sampleBtn.innerHTML = '✅ 공식 데이터셋 탑재 완료!';
        sampleBtn.style.background = '#047857';

        // 질문창으로 부드럽게 이동
        setTimeout(() => {
            document.getElementById('ask-section').scrollIntoView({ behavior: 'smooth' });
        }, 300);

        // 추천 분석 로드
        requestSuggestions();

    } catch (err) {
        addDebugLog('[ERROR]', `샘플 데이터 로드 오류: ${err.message}`);
        alert(`샘플 데이터 로드 오류: ${err.message}`);
        sampleBtn.innerHTML = originalText;
        sampleBtn.disabled = false;
    }
}

function handleFileSelect(file) {
    if (!file.name.toLowerCase().endsWith('.csv')) {
        alert('CSV 파일(.csv)만 업로드할 수 있습니다.');
        addDebugLog('[ERROR]', '잘못된 파일 확장자 업로드 시도: ' + file.name);
        return;
    }

    appState.currentFile = file;
    addDebugLog('[UPLOAD]', `파일 선택 완료: name=${file.name}, size=${file.size} bytes`);

    uploadAndInspectFile(file);
}

async function uploadAndInspectFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    addDebugLog('[INSPECT]', `진단 요청 시작: ${file.name}`);

    const inspectPanel = document.getElementById('inspect-result-panel');
    inspectPanel.classList.remove('hidden-panel');
    document.getElementById('diag-filename').textContent = '분석 중...';

    try {
        const res = await fetch('/inspect', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `진단 실패 (HTTP ${res.status})`);

        appState.inspectResult = data;
        addDebugLog('[INSPECT]', `진단 응답 수신 성공: rows=${data.rows}, cols=${data.columns}, warnings=${data.warnings.length}`);

        renderInspectResult(data);

        // 자연어 질문창(Ask AI)과 추천 분석(Step 2) 동시 활성화
        document.getElementById('ask-section').classList.remove('disabled-section');
        document.getElementById('step-2-section').classList.remove('disabled-section');

        // 자동으로 추천 분석 1회 로드
        requestSuggestions();

    } catch (err) {
        addDebugLog('[ERROR]', `진단 요청 중 오류 발생: ${err.message}`);
        alert(`진단 오류: ${err.message}`);
    }
}

function renderInspectResult(data) {
    document.getElementById('diag-filename').textContent = `${data.filename} (${data.file_size_kb} KB)`;
    document.getElementById('diag-encoding').textContent = `${data.encoding} (건너뛴 줄: ${data.skipped_rows})`;
    document.getElementById('diag-shape').textContent = `${data.rows.toLocaleString()}행 × ${data.columns}열`;
    document.getElementById('diag-rec-year').textContent = data.recommended_year ? `${data.recommended_year}년` : '감지 불가';

    const warningBox = document.getElementById('diag-warnings-container');
    const warningList = document.getElementById('diag-warnings-list');
    warningList.innerHTML = '';

    if (data.warnings && data.warnings.length > 0) {
        data.warnings.forEach(w => {
            const li = document.createElement('li');
            li.textContent = w;
            warningList.appendChild(li);
        });
        warningBox.classList.remove('hidden-panel');
    } else {
        warningBox.classList.add('hidden-panel');
    }

    const tagContainer = document.getElementById('diag-sector-tags');
    tagContainer.innerHTML = '';
    const sectors = data.emission_sector_columns || [];
    sectors.forEach(sec => {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = `${toKoName(sec)} (${sec})`;
        tagContainer.appendChild(span);
    });

    renderPreviewTable(data.preview, data.column_names);
}

function renderPreviewTable(rows, columns) {
    const theadTr = document.getElementById('preview-thead-tr');
    const tbody = document.getElementById('preview-tbody');
    theadTr.innerHTML = '';
    tbody.innerHTML = '';

    if (!rows || rows.length === 0) return;

    columns.forEach(col => {
        const th = document.createElement('th');
        const ko = toKoName(col);
        th.textContent = (ko !== col) ? `${ko} (${col})` : col;
        theadTr.appendChild(th);
    });

    rows.forEach(r => {
        const tr = document.createElement('tr');
        columns.forEach(col => {
            const td = document.createElement('td');
            const val = r[col];
            td.textContent = (val !== null && val !== undefined) ? val : '-';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
}

// ==========================================================================
// 5. 신규: 자연어 질문 처리 및 시각화 버튼 연동 (/ask)
// ==========================================================================
async function handleUserAsk() {
    const input = document.getElementById('ask-input');
    const query = input.value.trim();
    if (!query) {
        alert('질문 내용을 입력해 주세요.');
        return;
    }

    addDebugLog('[ASK]', `자연어 질문 시작: "${query}"`);

    const loading = document.getElementById('ask-loading');
    const answerBox = document.getElementById('ask-answer-box');
    const answerText = document.getElementById('ask-answer-text');
    const visAction = document.getElementById('ask-vis-action');

    loading.classList.remove('hidden-panel');
    answerBox.classList.add('hidden-panel');
    visAction.classList.add('hidden-panel');

    try {
        const res = await fetch('/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '답변 생성 실패');

        answerText.innerHTML = `<p>${data.answer.replace(/\n/g, '<br>')}</p>`;
        answerBox.classList.remove('hidden-panel');

        if (data.can_visualize && data.recommended_tool) {
            appState.customVisData = data;
            document.getElementById('ask-vis-title').textContent = `📊 ${data.visualization_title || '맞춤 시각화가 준비되었습니다!'}`;
            document.getElementById('ask-vis-desc').textContent = `도구: ${data.recommended_tool} | 기준시점: ${data.params?.reference_period || '자동'}`;
            visAction.classList.remove('hidden-panel');
        } else {
            appState.customVisData = null;
        }

        addDebugLog('[ASK]', '자연어 질문 답변 수신 완료');

    } catch (err) {
        addDebugLog('[ERROR]', `자연어 질문 오류: ${err.message}`);
        alert(`질문 처리 중 오류: ${err.message}`);
    } finally {
        loading.classList.add('hidden-panel');
    }
}

// ==========================================================================
// 6. Step 2: Gemini 분석 제안 요청 (/suggest)
// ==========================================================================
async function requestSuggestions() {
    addDebugLog('[SUGGEST]', '제안 요청 시작');
    const loading = document.getElementById('suggest-loading');
    const container = document.getElementById('suggestions-container');

    loading.classList.remove('hidden-panel');
    container.innerHTML = '';

    try {
        const res = await fetch('/suggest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `제안 요청 실패 (HTTP ${res.status})`);

        appState.suggestions = data.suggestions || [];
        addDebugLog('[SUGGEST]', `제안 응답 수신 성공: 제안 개수=${appState.suggestions.length}`);

        renderSuggestions(appState.suggestions);

    } catch (err) {
        addDebugLog('[ERROR]', `제안 요청 실패: ${err.message}`);
    } finally {
        loading.classList.add('hidden-panel');
    }
}

function renderSuggestions(suggestions) {
    const container = document.getElementById('suggestions-container');
    container.innerHTML = '';

    if (suggestions.length === 0) {
        container.innerHTML = '<p class="notice-box">생성된 제안이 없습니다.</p>';
        return;
    }

    suggestions.forEach((sugg) => {
        const card = document.createElement('div');
        card.className = 'suggestion-card';
        card.innerHTML = `
            <div>
                <span class="sugg-tool-name">도구: ${sugg.tool}</span>
                <h4 class="sugg-why">${sugg.why}</h4>
                <div class="sugg-caution">⚠️ ${sugg.caution}</div>
            </div>
            <div class="sugg-footer">
                <span>기준 시점: <strong>${sugg.reference_period || '자동'}</strong></span>
                <button class="btn btn-outline-sm btn-select-run">선택하여 실행 ➔</button>
            </div>
        `;

        card.querySelector('.btn-select-run').addEventListener('click', (e) => {
            e.stopPropagation();
            document.querySelectorAll('.suggestion-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            appState.selectedSuggestion = sugg;
            runSelectedTool(sugg);
        });

        container.appendChild(card);
    });
}

// ==========================================================================
// 7. Step 3: Pandas 계산 및 차트 렌더링 (/run)
// ==========================================================================
async function runSelectedTool(suggestion) {
    addDebugLog('[RUN]', `도구 실행 시작: tool=${suggestion.tool}, period=${suggestion.reference_period}`);

    const step3 = document.getElementById('step-3-section');
    step3.classList.remove('disabled-section');
    step3.scrollIntoView({ behavior: 'smooth' });

    const loading = document.getElementById('run-loading');
    const container = document.getElementById('run-result-container');
    loading.classList.remove('hidden-panel');
    container.classList.add('hidden-panel');

    try {
        const res = await fetch('/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tool: suggestion.tool,
                params: suggestion.params || {}
            })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `도구 실행 실패 (HTTP ${res.status})`);

        appState.runResult = data;
        addDebugLog('[RUN]', `도구 결과 수신 완료: 사용 행=${data.used_rows}, 제외 행=${data.excluded_rows}`);

        renderRunResult(data);
        container.classList.remove('hidden-panel');

    } catch (err) {
        addDebugLog('[ERROR]', `도구 실행 오류: ${err.message}`);
        alert(`분석 계산 오류: ${err.message}`);
    } finally {
        loading.classList.add('hidden-panel');
    }
}

function renderRunResult(data) {
    document.getElementById('receipt-tool').textContent = data.tool;
    document.getElementById('receipt-period').textContent = data.reference_period;
    document.getElementById('receipt-used-rows').textContent = `${data.used_rows.toLocaleString()} 건`;
    document.getElementById('receipt-excluded-rows').textContent = `${data.excluded_rows.toLocaleString()} 건`;
    document.getElementById('receipt-unit').textContent = data.unit;
    document.getElementById('receipt-reason-text').textContent = data.exclusion_reason;
    document.getElementById('receipt-caution-text').textContent = data.caution;

    if (data.chart) {
        renderChart(data.chart);
    }
    renderRunSummaryTable(data);
}

function renderChart(chartConfig) {
    const canvas = document.getElementById('analysis-chart');
    const ctx = canvas.getContext('2d');

    if (currentChartInstance) {
        currentChartInstance.destroy();
    }

    const defaultColors = [
        '#059669', '#0d9488', '#2563eb', '#7c3aed', '#db2777',
        '#ea580c', '#ca8a04', '#16a34a', '#0891b2', '#4f46e5'
    ];

    const datasets = (chartConfig.datasets || []).map((ds, idx) => {
        const baseColor = defaultColors[idx % defaultColors.length];
        return {
            label: ds.label || '배출량',
            data: ds.data,
            backgroundColor: chartConfig.type === 'line' ? 'transparent' : (chartConfig.type === 'pie' ? defaultColors : baseColor),
            borderColor: baseColor,
            borderWidth: 2,
            fill: false,
            tension: 0.2
        };
    });

    const isHorizontal = (chartConfig.indexAxis === 'y');

    currentChartInstance = new Chart(ctx, {
        type: chartConfig.type || 'bar',
        data: {
            labels: chartConfig.labels || [],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: isHorizontal ? 'y' : 'x',
            plugins: {
                title: {
                    display: !!chartConfig.title,
                    text: chartConfig.title || '',
                    font: { size: 14, weight: 'bold' }
                },
                legend: {
                    display: datasets.length > 1 || chartConfig.type === 'pie'
                }
            },
            scales: chartConfig.type === 'pie' ? {} : {
                y: { beginAtZero: true }
            }
        }
    });

    addDebugLog('[CHART]', `차트 렌더 완료 (종류=${chartConfig.type})`);
}

function renderRunSummaryTable(data) {
    const thead = document.getElementById('run-table-head');
    const tbody = document.getElementById('run-table-body');
    thead.innerHTML = '';
    tbody.innerHTML = '';

    const d = data.data;
    if (!d) return;

    if (d.ranking && Array.isArray(d.ranking)) {
        thead.innerHTML = `<tr><th>순위</th><th>국가 / 대상</th><th>배출량 (${data.unit})</th></tr>`;
        d.ranking.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td><strong>${r.rank}</strong></td><td>${r.label}</td><td>${Number(r.value).toLocaleString()}</td>`;
            tbody.appendChild(tr);
        });
    } else if (d.summary && Array.isArray(d.summary)) {
        thead.innerHTML = `<tr><th>부문 / 그룹</th><th>총합계 (${data.unit})</th><th>평균</th><th>데이터 수</th></tr>`;
        d.summary.forEach(s => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td><strong>${s.group}</strong></td><td>${Number(s.sum).toLocaleString()}</td><td>${Number(s.mean).toLocaleString()}</td><td>${s.count}</td>`;
            tbody.appendChild(tr);
        });
    } else if (d.top_increases && Array.isArray(d.top_increases)) {
        thead.innerHTML = `<tr><th>국가</th><th>시작 연도 배출량</th><th>종료 연도 배출량</th><th>변화량</th><th>변화율(%)</th></tr>`;
        d.top_increases.forEach(item => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td><strong>${item.entity}</strong></td><td>${Number(item.start_val).toLocaleString()}</td><td>${Number(item.end_val).toLocaleString()}</td><td>${Number(item.abs_change).toLocaleString()}</td><td>${item.pct_change > 0 ? '+' : ''}${item.pct_change}%</td>`;
            tbody.appendChild(tr);
        });
    }
}

// ==========================================================
// 8. Step 4: Gemini 해석 보고서 (/explain)
// ==========================================================
async function requestExplanation() {
    const selectedMode = document.querySelector('input[name="explain-mode"]:checked').value;
    addDebugLog('[EXPLAIN]', `해석 요청 시작 (모드=${selectedMode})`);

    const loading = document.getElementById('explain-loading');
    const container = document.getElementById('explain-result-container');
    loading.classList.remove('hidden-panel');
    container.classList.add('hidden-panel');

    try {
        const res = await fetch('/explain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: selectedMode,
                result: appState.runResult
            })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `보고서 생성 실패 (HTTP ${res.status})`);

        appState.lastExplanation = data.explanation;
        addDebugLog('[EXPLAIN]', `해석 응답 수신 성공 (길이=${data.explanation.length})`);

        renderReportMarkdown(data.explanation, selectedMode);
        container.classList.remove('hidden-panel');
        container.scrollIntoView({ behavior: 'smooth' });

    } catch (err) {
        addDebugLog('[ERROR]', `해석 생성 실패: ${err.message}`);
        alert(`보고서 생성 오류: ${err.message}`);
    } finally {
        loading.classList.add('hidden-panel');
    }
}

function renderReportMarkdown(rawText, mode) {
    const titleEl = document.getElementById('report-title');
    titleEl.textContent = mode === 'B' 
        ? '📋 [모드 B] Pandas 정밀 계산 기반 온실가스 해석 보고서 (공식)'
        : '⚠️ [모드 A] 단순 추정 보고서 (비교용 허술한 모드)';

    const contentEl = document.getElementById('report-content');
    
    let html = rawText
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
        .replace(/^\* (.*$)/gim, '<li>$1</li>')
        .replace(/^- (.*$)/gim, '<li>$1</li>')
        .replace(/\n\n+/g, '</p><p>');

    contentEl.innerHTML = `<p>${html}</p>`;
}

// ==========================================================
// 9. 신규: 보고서 기반 실시간 대화형 Q&A 챗봇 (/chat)
// ==========================================================
async function handleChatSend() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    const messageList = document.getElementById('chat-messages');

    // 사용자 말풍선 추가
    const userBubble = document.createElement('div');
    userBubble.className = 'chat-bubble chat-bubble-user';
    userBubble.textContent = message;
    messageList.appendChild(userBubble);
    messageList.scrollTop = messageList.scrollHeight;

    // AI 대기 말풍선 추가
    const aiBubble = document.createElement('div');
    aiBubble.className = 'chat-bubble chat-bubble-ai';
    aiBubble.textContent = '답변 작성 중...';
    messageList.appendChild(aiBubble);
    messageList.scrollTop = messageList.scrollHeight;

    addDebugLog('[CHAT]', `보고서 질의 전송: "${message}"`);

    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                report: appState.lastExplanation
            })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '답변 수신 실패');

        aiBubble.innerHTML = data.reply.replace(/\n/g, '<br>');
        messageList.scrollTop = messageList.scrollHeight;
        addDebugLog('[CHAT]', '보고서 챗봇 답변 완료');

    } catch (err) {
        aiBubble.textContent = `오류 발생: ${err.message}`;
        addDebugLog('[ERROR]', `챗봇 오류: ${err.message}`);
    }
}

function copyReportToClipboard() {
    if (!appState.lastExplanation) {
        alert('복사할 보고서 내용이 없습니다.');
        return;
    }
    navigator.clipboard.writeText(appState.lastExplanation).then(() => {
        alert('보고서 내용이 클립보드에 복사되었습니다!');
    });
}

function copyDebugInfo() {
    const pre = document.getElementById('debug-status-pre');
    navigator.clipboard.writeText(pre.textContent).then(() => {
        alert('디버그 상태 정보가 복사되었습니다. AI에게 그대로 질문하시면 됩니다!');
    });
}
