import io
import os
import csv
import json
import logging
import math
import re
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
from google import genai

import tools

# .env 환경변수 로드
load_dotenv()

# 로깅 설정 (규칙: print() 대신 Python logging 모듈 사용)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('ghg-insight-builder')

app = Flask(__name__)

# 환경변수 로드
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
MAX_UPLOAD_MB = int(os.getenv('MAX_UPLOAD_MB', 10))
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024

# 메모리 데이터셋 보관소 (디스크 영구 저장 안 함, 단 1개 데이터셋 유지)
CURRENT_DATASET = {
    'df': None,
    'meta': None,
    'last_run_result': None,
    'last_explanation': None,
    'chat_history': []
}

ENCODINGS_TO_TRY = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']

# 12대 분석 도구 카탈로그 메타데이터 정의
TOOL_CATALOG = [
    {"tool": "reshape_wide_to_long", "description": "연도/부문 열을 행으로 접기", "params_spec": {"var_name": "Sector", "value_name": "Emissions"}},
    {"tool": "quality_report", "description": "결측·중복·타입·음수 배출량 무결성 진단", "params_spec": {}},
    {"tool": "year_coverage", "description": "연도별 값 개수와 권장 기준연도 확인", "params_spec": {}},
    {"tool": "detect_aggregates", "description": "전 세계 총합 및 지역별 집계 행 감지", "params_spec": {}},
    {"tool": "describe_numeric", "description": "온실가스 배출량 수치형 열 통계 (평균·중앙값·최소·최대·표준편차)", "params_spec": {"reference_period": "str (예: 2023)", "exclude_aggregates": True}},
    {"tool": "trend_line", "description": "국가 또는 부문별 온실가스 배출량 연도별 추이 (선 차트)", "params_spec": {"sectors": "list of str", "entities": "list of str", "exclude_aggregates": False}},
    {"tool": "top_bottom_n", "description": "기준연도 기준 온실가스 배출 상위·하위 N개 국가 (수평 막대)", "params_spec": {"value_column": "str", "reference_period": "str (필수)", "n": 10, "mode": "top", "exclude_aggregates": True}},
    {"tool": "group_summary", "description": "부문별/그룹별 온실가스 평균·합계·개수 비교 (막대)", "params_spec": {"reference_period": "str (필수)", "exclude_aggregates": True}},
    {"tool": "change_rate", "description": "두 시점 사이 부문별 온실가스 변화량·변화율 (막대)", "params_spec": {"sector_column": "str", "start_period": "str (필수)", "end_period": "str (필수)", "n": 10, "exclude_aggregates": True}},
    {"tool": "distribution", "description": "배출량 구간별 국가 분포 (히스토그램)", "params_spec": {"value_column": "str", "reference_period": "str (필수)", "bins": 8, "exclude_aggregates": True}},
    {"tool": "correlation_scatter", "description": "두 온실가스 부문 간 상관계수 (산점도)", "params_spec": {"x_column": "str", "y_column": "str", "reference_period": "str (필수)", "exclude_aggregates": True}},
    {"tool": "compare_one_vs_all", "description": "특정 국가 vs 전체 평균·중앙값 비교 (강조 막대)", "params_spec": {"target_entity": "str (예: South Korea)", "value_column": "str", "reference_period": "str (필수)", "exclude_aggregates": True}}
]

TOOL_FUNCTION_MAP = {
    "reshape_wide_to_long": tools.reshape_wide_to_long,
    "quality_report": tools.quality_report,
    "year_coverage": tools.year_coverage,
    "detect_aggregates": tools.detect_aggregates,
    "describe_numeric": tools.describe_numeric,
    "trend_line": tools.trend_line,
    "top_bottom_n": tools.top_bottom_n,
    "group_summary": tools.group_summary,
    "change_rate": tools.change_rate,
    "distribution": tools.distribution,
    "correlation_scatter": tools.correlation_scatter,
    "compare_one_vs_all": tools.compare_one_vs_all
}

def detect_header_and_read(raw_bytes):
    """인코딩 순차 시도 및 헤더 감지"""
    decoded_text = None
    successful_encoding = None

    for enc in ENCODINGS_TO_TRY:
        try:
            decoded_text = raw_bytes.decode(enc)
            successful_encoding = enc
            logger.info(f'[ENCODING] {enc} 시도 성공')
            break
        except (UnicodeDecodeError, LookupError) as e:
            logger.info(f'[ENCODING] {enc} 시도 실패: {e}')

    if not successful_encoding or decoded_text is None:
        raise ValueError('지원하는 인코딩(utf-8-sig, utf-8, cp949, euc-kr)으로 파일을 읽을 수 없습니다.')

    lines = decoded_text.splitlines()
    if not lines:
        raise ValueError('CSV 파일이 비어 있습니다.')

    skipped_rows = 0
    header_found = False

    for idx, line in enumerate(lines[:25]):
        if not line.strip():
            continue
        try:
            reader = csv.reader([line])
            row = next(reader)
        except Exception:
            continue

        non_empty = [col.strip() for col in row if col.strip()]
        if len(non_empty) >= 2:
            num_numeric = sum(1 for col in non_empty if col.replace('.', '', 1).replace('-', '', 1).isdigit())
            if (len(non_empty) - num_numeric) / len(non_empty) >= 0.5:
                skipped_rows = idx
                header_found = True
                break

    if not header_found:
        logger.warning('[HEADER] 헤더 줄을 특정하지 못해 0번째 줄을 헤더로 사용합니다.')
        skipped_rows = 0

    logger.info(f'[HEADER] 헤더 줄 감지 결과 (건너뛴 줄 수: {skipped_rows})')

    buffer = io.StringIO(decoded_text)
    df = pd.read_csv(buffer, skiprows=skipped_rows)
    return df, successful_encoding, skipped_rows

def sanitize_for_json(obj):
    """NaN, Infinity 등을 JSON에서 안전하게 파싱 가능한 None/null로 변환"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    elif isinstance(obj, (np.floating, np.integer)):
        val = obj.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj

@app.route('/', methods=['GET'])
def index():
    """메인 HTML 대시보드 페이지 반환"""
    logger.info('[REQUEST] GET /')
    return render_template('index.html')

@app.route('/health', methods=['GET'])
def health():
    """서버 상태와 API Key 설정 여부만 반환 (키 값은 반환 금지)"""
    logger.info('[REQUEST] GET /health')
    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    api_key_configured = bool(api_key and api_key != 'your_gemini_api_key_here')

    response_data = {
        'status': 'ok',
        'api_key_configured': api_key_configured,
        'model': GEMINI_MODEL
    }
    logger.info(f'[RESPONSE] status=200 api_key_configured={api_key_configured} model={GEMINI_MODEL}')
    return jsonify(response_data), 200

@app.route('/inspect', methods=['POST'])
def inspect_file():
    """CSV 업로드, 14개 종합 진단 결과 JSON 반환"""
    logger.info('[REQUEST] POST /inspect')

    if 'file' not in request.files:
        logger.error('[ERROR] 요청에 파일이 첨부되지 않았습니다.')
        return jsonify({'error': '업로드할 CSV 파일을 선택해 주세요.'}), 400

    file = request.files['file']
    filename = file.filename or ''

    if not filename:
        logger.error('[ERROR] 파일명이 비어 있습니다.')
        return jsonify({'error': '선택된 파일이 없습니다.'}), 400

    if not filename.lower().endswith('.csv'):
        logger.error(f'[ERROR] 허용되지 않는 파일 형식: {filename}')
        return jsonify({'error': 'CSV 파일(.csv)만 업로드할 수 있습니다.'}), 400

    raw_bytes = file.read()
    file_size_bytes = len(raw_bytes)
    logger.info(f'[FILE] name={filename} size={file_size_bytes}')

    if file_size_bytes == 0:
        logger.error('[ERROR] 빈 파일입니다.')
        return jsonify({'error': '업로드된 파일이 비어 있습니다 (0 바이트).'}), 400

    try:
        df, successful_encoding, skipped_rows = detect_header_and_read(raw_bytes)
    except Exception as e:
        logger.error(f'[ERROR] CSV 파싱 실패: {str(e)}')
        return jsonify({'error': f'파일을 분석하는 중 오류가 발생했습니다: {str(e)}'}), 400

    rows_count, cols_count = df.shape
    columns = [str(col).strip() for col in df.columns]
    df.columns = columns
    logger.info(f'[CSV] parsing 완료 rows={rows_count} columns={cols_count}')

    warnings = []

    dtypes = {col: str(df[col].dtype) for col in columns}
    numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
    string_columns = df.select_dtypes(exclude=[np.number]).columns.tolist()

    year_candidates = []
    for col in columns:
        col_lower = col.lower()
        if any(keyword in col_lower for keyword in ['year', 'date', '연도', '날짜', 'yr', 'time']):
            year_candidates.append(col)
        elif col in numeric_columns:
            sample_vals = df[col].dropna()
            if not sample_vals.empty and sample_vals.between(1800, 2100).all() and (sample_vals % 1 == 0).all():
                if col not in year_candidates:
                    year_candidates.append(col)

    entity_candidates = []
    code_candidates = []
    sector_candidates = []
    for col in columns:
        col_lower = col.lower()
        if any(k in col_lower for k in ['entity', 'country', 'nation', 'region', '국가', '지역']):
            entity_candidates.append(col)
        if any(k in col_lower for k in ['code', 'iso', '코드']):
            code_candidates.append(col)
        if any(k in col_lower for k in ['sector', '부문', 'category']):
            sector_candidates.append(col)

    if not entity_candidates and string_columns:
        entity_candidates.append(string_columns[0])

    emission_sector_columns = [col for col in numeric_columns if col not in year_candidates]

    missing_stats = {}
    for col in columns:
        null_count = int(df[col].isna().sum())
        null_pct = round((null_count / rows_count) * 100, 2) if rows_count > 0 else 0.0
        missing_stats[col] = {
            'count': null_count,
            'ratio_pct': null_pct
        }

    duplicate_rows_count = int(df.duplicated().sum())
    if duplicate_rows_count > 0:
        warnings.append(f'중복된 행이 {duplicate_rows_count}건 존재합니다.')

    unnamed_cols = [col for col in columns if 'unnamed' in col.lower() or not col]
    completely_empty_cols = [col for col in columns if df[col].isna().all()]
    if unnamed_cols:
        warnings.append(f'이름이 없거나 자동 생성된 열: {unnamed_cols}')
    if completely_empty_cols:
        warnings.append(f'전체 값이 비어 있는 열: {completely_empty_cols}')

    year_coverage = {}
    recommended_year = None
    detected_year_col = year_candidates[0] if year_candidates else None

    if detected_year_col:
        try:
            year_counts = df[detected_year_col].dropna().value_counts().sort_index()
            year_coverage = {str(int(k) if isinstance(k, (int, float, np.integer, np.floating)) else k): int(v) 
                             for k, v in year_counts.items()}
            if year_coverage:
                max_cnt = max(year_coverage.values())
                qualifying_years = [y for y, cnt in year_coverage.items() if cnt >= max_cnt * 0.8]
                if qualifying_years:
                    try:
                        recommended_year = str(max(int(y) for y in qualifying_years))
                    except ValueError:
                        recommended_year = str(qualifying_years[-1])
        except Exception as e:
            logger.warning(f'연도 충실도 계산 중 예외 발생: {e}')

    aggregate_rows_count = 0
    aggregate_samples = []
    main_entity_col = entity_candidates[0] if entity_candidates else None
    main_code_col = code_candidates[0] if code_candidates else None

    if main_entity_col:
        agg_mask = df.apply(lambda r: tools.is_aggregate_row(r[main_entity_col], r[main_code_col] if main_code_col else None), axis=1)
        aggregate_rows_count = int(agg_mask.sum())
        aggregate_samples = df.loc[agg_mask, main_entity_col].dropna().unique().tolist()[:10]
        if aggregate_rows_count > 0:
            warnings.append(f'전 세계/대륙/소득군 집계 행으로 추정되는 행이 {aggregate_rows_count}건 감지되었습니다. (국가별 분석 시 제외 권장)')

    preview_df = df.head(10).copy()
    preview_rows = preview_df.replace({np.nan: None}).to_dict(orient='records')
    preview_rows = sanitize_for_json(preview_rows)

    CURRENT_DATASET['df'] = df
    CURRENT_DATASET['meta'] = {
        'filename': filename,
        'file_size_bytes': file_size_bytes,
        'encoding': successful_encoding,
        'skipped_rows': skipped_rows,
        'rows': rows_count,
        'columns': cols_count,
        'column_names': columns,
        'numeric_columns': numeric_columns,
        'string_columns': string_columns,
        'year_col': detected_year_col,
        'entity_col': main_entity_col,
        'code_col': main_code_col,
        'emission_sectors': emission_sector_columns,
        'recommended_year': recommended_year,
        'year_coverage': year_coverage
    }
    CURRENT_DATASET['last_run_result'] = None
    CURRENT_DATASET['last_explanation'] = None
    CURRENT_DATASET['chat_history'] = []

    response_payload = {
        'filename': filename,
        'file_size_bytes': file_size_bytes,
        'file_size_kb': round(file_size_bytes / 1024, 2),
        'encoding': successful_encoding,
        'skipped_rows': skipped_rows,
        'rows': rows_count,
        'columns': cols_count,
        'column_names': columns,
        'dtypes': dtypes,
        'numeric_columns': numeric_columns,
        'string_columns': string_columns,
        'year_candidates': year_candidates,
        'detected_year_column': detected_year_col,
        'entity_candidates': entity_candidates,
        'code_candidates': code_candidates,
        'sector_candidates': sector_candidates,
        'emission_sector_columns': emission_sector_columns,
        'missing_stats': missing_stats,
        'duplicate_rows': duplicate_rows_count,
        'unnamed_columns': unnamed_cols,
        'empty_columns': completely_empty_cols,
        'year_coverage': year_coverage,
        'recommended_year': recommended_year,
        'aggregate_rows_count': aggregate_rows_count,
        'aggregate_samples': aggregate_samples,
        'preview': preview_rows,
        'warnings': warnings,
        'notice': '파일은 디스크에 저장되지 않으며 메모리에만 보관됩니다. 서버를 재시작하면 데이터셋이 초기화됩니다.'
    }

    logger.info(f'[DIAGNOSE] 진단 완료 warnings={len(warnings)}')
    return jsonify(sanitize_for_json(response_payload)), 200

# ==========================================================
# 신규 추가: POST /load-sample (발표/데모용 원클릭 샘플 데이터 로드)
# ==========================================================
@app.route('/load-sample', methods=['POST'])
def load_sample_dataset():
    """발표 및 시연용으로 data 폴더의 공식 온실가스 CSV를 즉시 진단하여 로드합니다."""
    logger.info('[REQUEST] POST /load-sample')
    sample_path = os.path.join(os.path.dirname(__file__), 'data', 'ghg-emissions-by-sector.csv')
    if not os.path.exists(sample_path):
        return jsonify({'error': 'data 폴더에 ghg-emissions-by-sector.csv 파일이 없습니다.'}), 404

    with open(sample_path, 'rb') as f:
        raw_bytes = f.read()

    file_size_bytes = len(raw_bytes)
    filename = 'ghg-emissions-by-sector.csv'

    try:
        df, successful_encoding, skipped_rows = detect_header_and_read(raw_bytes)
    except Exception as e:
        logger.error(f'[ERROR] 샘플 CSV 파싱 실패: {str(e)}')
        return jsonify({'error': f'샘플 데이터를 읽는 중 오류: {str(e)}'}), 500

    rows_count, cols_count = df.shape
    columns = [str(col).strip() for col in df.columns]
    df.columns = columns

    warnings = []
    dtypes = {col: str(df[col].dtype) for col in columns}
    numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
    string_columns = df.select_dtypes(exclude=[np.number]).columns.tolist()

    year_candidates = ['Year'] if 'Year' in columns else []
    entity_candidates = ['Entity'] if 'Entity' in columns else []
    code_candidates = ['Code'] if 'Code' in columns else []
    sector_candidates = [col for col in numeric_columns if col not in year_candidates]

    missing_stats = {}
    for col in columns:
        null_count = int(df[col].isna().sum())
        null_pct = round((null_count / rows_count) * 100, 2) if rows_count > 0 else 0.0
        missing_stats[col] = {'count': null_count, 'ratio_pct': null_pct}

    duplicate_rows_count = int(df.duplicated().sum())

    year_counts = df['Year'].dropna().value_counts().sort_index()
    year_coverage = {str(int(k)): int(v) for k, v in year_counts.items()}
    recommended_year = '2023'

    agg_mask = df.apply(lambda r: tools.is_aggregate_row(r['Entity'], r['Code'] if 'Code' in df.columns else None), axis=1)
    aggregate_rows_count = int(agg_mask.sum())
    aggregate_samples = df.loc[agg_mask, 'Entity'].dropna().unique().tolist()[:10]
    warnings.append(f'전 세계/대륙/소득군 집계 행으로 추정되는 행이 {aggregate_rows_count}건 감지되었습니다. (국가별 분석 시 제외 권장)')

    preview_df = df.head(10).copy()
    preview_rows = preview_df.replace({np.nan: None}).to_dict(orient='records')

    CURRENT_DATASET['df'] = df
    CURRENT_DATASET['meta'] = {
        'filename': filename,
        'file_size_bytes': file_size_bytes,
        'encoding': successful_encoding,
        'skipped_rows': skipped_rows,
        'rows': rows_count,
        'columns': cols_count,
        'column_names': columns,
        'numeric_columns': numeric_columns,
        'string_columns': string_columns,
        'year_col': 'Year',
        'entity_col': 'Entity',
        'code_col': 'Code' if 'Code' in columns else None,
        'emission_sectors': sector_candidates,
        'recommended_year': recommended_year,
        'year_coverage': year_coverage
    }
    CURRENT_DATASET['last_run_result'] = None
    CURRENT_DATASET['last_explanation'] = None
    CURRENT_DATASET['chat_history'] = []

    response_payload = {
        'filename': filename,
        'file_size_bytes': file_size_bytes,
        'file_size_kb': round(file_size_bytes / 1024, 2),
        'encoding': successful_encoding,
        'skipped_rows': skipped_rows,
        'rows': rows_count,
        'columns': cols_count,
        'column_names': columns,
        'dtypes': dtypes,
        'numeric_columns': numeric_columns,
        'string_columns': string_columns,
        'year_candidates': year_candidates,
        'detected_year_column': 'Year',
        'entity_candidates': entity_candidates,
        'code_candidates': code_candidates,
        'sector_candidates': sector_candidates,
        'emission_sector_columns': sector_candidates,
        'missing_stats': missing_stats,
        'duplicate_rows': duplicate_rows_count,
        'unnamed_columns': [],
        'empty_columns': [],
        'year_coverage': year_coverage,
        'recommended_year': recommended_year,
        'aggregate_rows_count': aggregate_rows_count,
        'aggregate_samples': aggregate_samples,
        'preview': preview_rows,
        'warnings': warnings,
        'notice': '공식 샘플 데이터셋이 메모리에 성공적으로 로드되었습니다.'
    }

    logger.info('[DIAGNOSE] 샘플 데이터 로드 및 진단 완료')
    return jsonify(sanitize_for_json(response_payload)), 200

# ==========================================================
# 신규 추가: POST /ask (자연어 질문 기반 답변 & 시각화 자동 매핑)
# ==========================================================
@app.route('/ask', methods=['POST'])
def ask_question():
    """
    사용자의 자연어 질문을 받아 데이터셋 기반 답변을 생성하고,
    해당 질문을 해결할 수 있는 최적의 도구와 파라미터를 추천하여
    시각화 버튼을 활성화할 수 있는 메타데이터를 반환합니다.
    """
    logger.info('[REQUEST] POST /ask')

    if CURRENT_DATASET['df'] is None or CURRENT_DATASET['meta'] is None:
        return jsonify({'error': '먼저 CSV 파일을 업로드하여 진단(/inspect)을 완료해 주세요.'}), 400

    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key or api_key == 'your_gemini_api_key_here':
        return jsonify({'error': 'Gemini API Key가 설정되지 않았습니다.'}), 401

    req_data = request.get_json(silent=True) or {}
    user_query = req_data.get('query', '').strip()
    if not user_query:
        return jsonify({'error': '질문 내용을 입력해 주세요.'}), 400

    meta = CURRENT_DATASET['meta']
    emission_sectors = meta.get('emission_sectors', [])
    recommended_year = meta.get('recommended_year') or '2023'
    entity_col = meta.get('entity_col') or 'Entity'
    year_col = meta.get('year_col') or 'Year'

    prompt = f"""
당신은 온실가스 배출량 전문 데이터 분석가이자 친절한 설명자입니다.
사용자가 현재 로드된 온실가스 데이터에 대해 질문했습니다:
"{user_query}"

[현재 데이터셋 메타데이터]
- 파일명: {meta.get('filename')}
- 총 행 수: {meta.get('rows')}
- 사용 가능한 열 목록: {meta.get('column_names')}
- 11개 배출 부문 열: {emission_sectors}
- 국가/개체 식별 열: {entity_col}
- 연도 열: {year_col} (권장 기준연도: {recommended_year})

[사용 가능한 분석 도구 목록]
{json.dumps(TOOL_CATALOG, ensure_ascii=False, indent=2)}

[답변 및 처리 규칙]
1. 데이터셋에 없는 항목(예: '인구 수(Population)', 'GDP', '기온', '전기차 보급률' 등)에 대해 묻는 경우:
   - "이 데이터셋에는 해당 항목(예: 인구 수) 데이터가 포함되어 있지 않습니다"라고 정확하고 솔직하게 답변하세요.
   - 단, 온실가스 부문 간의 관계나 배출 규모를 대신 확인할 수 있는 분석을 친절히 제안하세요.
   - 이 경우 can_visualize는 false로 두거나, 대체 가능한 도구가 있다면 제안하세요.
2. 질문이 데이터셋의 배출 부문이나 국가 비교로 해결 가능한 경우:
   - 중학생도 이해하기 쉽게 핵심을 설명하는 친절한 답변(answer)을 작성하세요.
   - 질문을 가장 잘 시각화할 수 있는 도구(recommended_tool)와 정확한 파라미터(params)를 JSON으로 구성하세요.
   - can_visualize를 true로 설정하세요.
3. 응답은 반드시 순수 JSON이어야 합니다.

[출력 JSON 규격]
{{
  "answer": "사용자 질문에 대한 친절한 설명 답변",
  "can_visualize": true,
  "visualization_title": "차트 제목 (예: 2023년 전기 및 열 생산 배출 상위 10개국 및 한국 비교)",
  "recommended_tool": "top_bottom_n",
  "params": {{
    "value_column": "Electricity and heat",
    "reference_period": "{recommended_year}",
    "n": 10,
    "mode": "top",
    "exclude_aggregates": true
  }}
}}
"""

    logger.info(f'[AI] 자연어 질문 처리 시작: "{user_query[:30]}..."')
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        response_text = response.text or ''
        clean_text = response_text.strip()
        if clean_text.startswith('```json'):
            clean_text = clean_text[7:]
        if clean_text.startswith('```'):
            clean_text = clean_text[3:]
        if clean_text.endswith('```'):
            clean_text = clean_text[:-3]

        parsed = json.loads(clean_text.strip())
        logger.info(f'[AI] 자연어 질문 응답 완료 (can_visualize={parsed.get("can_visualize")})')
        return jsonify(sanitize_for_json(parsed)), 200

    except Exception as e:
        logger.error(f'[ERROR] 자연어 질문 처리 오류: {e}', exc_info=True)
        return jsonify({'error': f'질문 분석 중 오류가 발생했습니다: {str(e)}'}), 500

# ==========================================================
# 신규 추가: POST /chat (Step 4 보고서 기반 대화형 챗봇)
# ==========================================================
@app.route('/chat', methods=['POST'])
def chat_with_report():
    """
    Step 4에서 생성된 보고서와 최근 계산 결과를 바탕으로
    사용자의 추가 궁금증이나 심층 질문에 대화형으로 답변합니다.
    """
    logger.info('[REQUEST] POST /chat')

    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key or api_key == 'your_gemini_api_key_here':
        return jsonify({'error': 'Gemini API Key가 설정되지 않았습니다.'}), 401

    req_data = request.get_json(silent=True) or {}
    user_message = req_data.get('message', '').strip()
    report_text = req_data.get('report') or CURRENT_DATASET.get('last_explanation', '')

    if not user_message:
        return jsonify({'error': '메시지 내용을 입력해 주세요.'}), 400

    last_run = CURRENT_DATASET.get('last_run_result') or {}

    prompt = f"""
당신은 방금 작성된 온실가스 데이터 분석 보고서의 해설자입니다.
사용자가 보고서를 읽고 다음과 같이 추가 질문을 하였습니다:
"{user_message}"

[최근 분석 보고서 본문]
{report_text[:2500] if report_text else "보고서 본문 없음"}

[최근 Pandas 계산 결과 요약]
{json.dumps(last_run.get('result', {}).get('data', {}), ensure_ascii=False)[:1000]}

[답변 원칙]
1. 보고서 내용과 계산 결과를 바탕으로 친절하고 명쾌하게 답변하세요.
2. 중학생도 이해할 수 있는 비유와 예시를 활용하세요.
3. 데이터에 없는 사실은 단정 짓지 말고 "이 데이터로는 확인할 수 없으나, 일반적인 환경 통계에서는..." 형태로 구분해 주세요.
4. 존댓말과 친근한 이모지를 적절히 사용하세요.
"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        reply = response.text or '답변을 생성하지 못했습니다.'
        return jsonify({'reply': reply}), 200

    except Exception as e:
        logger.error(f'[ERROR] 보고서 챗봇 응답 오류: {e}', exc_info=True)
        return jsonify({'error': f'챗봇 응답 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/suggest', methods=['POST'])
def suggest_analyses():
    """진단 결과 요약과 도구 카탈로그를 Gemini에 전달, 분석 제안 JSON 수신"""
    logger.info('[REQUEST] POST /suggest')

    if CURRENT_DATASET['df'] is None or CURRENT_DATASET['meta'] is None:
        logger.error('[ERROR] 진단된 데이터셋이 메모리에 없습니다.')
        return jsonify({'error': '먼저 CSV 파일을 업로드하여 진단(/inspect)을 완료해 주세요.'}), 400

    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key or api_key == 'your_gemini_api_key_here':
        logger.error('[ERROR] API Key가 설정되지 않았습니다.')
        return jsonify({'error': 'Gemini API Key가 설정되지 않았습니다. .env 파일에 올바른 키를 입력해 주세요.'}), 401

    meta = CURRENT_DATASET['meta']
    emission_sectors = meta.get('emission_sectors', [])
    recommended_year = meta.get('recommended_year') or '2023'
    entity_col = meta.get('entity_col') or 'Entity'
    year_col = meta.get('year_col') or 'Year'

    diagnostic_summary = {
        "filename": meta.get('filename'),
        "total_rows": meta.get('rows'),
        "columns": meta.get('column_names'),
        "emission_sector_columns": emission_sectors,
        "entity_column": entity_col,
        "year_column": year_col,
        "recommended_reference_year": recommended_year,
        "available_year_range": list(meta.get('year_coverage', {}).keys())[:5] + ["..."] + list(meta.get('year_coverage', {}).keys())[-5:]
    }

    prompt = f"""
당신은 온실가스 배출량 전문 데이터 분석가입니다.
사용자가 업로드한 온실가스 데이터의 진단 요약 정보와 사용 가능한 도구 카탈로그를 제공합니다.
이 데이터를 바탕으로 실제 사용자가 실행했을 때 가장 통찰력 있고 유의미한 분석 3~5개를 선정하여 제안하세요.

[절대 준수 규칙]
1. 반드시 아래 도구 카탈로그(Tool Catalog)에 있는 도구명만 'tool'로 지정해야 합니다. 없는 도구는 절대 제안할 수 없습니다.
2. 'params'에 들어가는 모든 열 이름(value_column, sector_column, x_column 등)은 반드시 진단 요약의 'emission_sector_columns' 목록에 존재하는 정확한 열 이름이어야 합니다.
3. 7~12번 도구는 reference_period(연도)가 필수입니다. 권장 기준연도('{recommended_year}') 또는 사용 가능한 연도를 지정하세요.
4. 9번 change_rate 도구는 start_period='1990', end_period='{recommended_year}' 형태로 설정하세요.
5. exclude_aggregates는 국가 간 비교 시 반드시 true로 설정하세요.
6. 응답은 반드시 마크다운 코드블록이나 잡담 없이 순수한 JSON 형식만 출력해야 합니다.
7. 제안 개수는 정확히 3~5개여야 합니다.

[사용 가능한 도구 카탈로그]
{json.dumps(TOOL_CATALOG, ensure_ascii=False, indent=2)}

[데이터셋 진단 요약]
{json.dumps(diagnostic_summary, ensure_ascii=False, indent=2)}

[출력 JSON 규격]
{{
  "suggestions": [
    {{
      "tool": "top_bottom_n",
      "params": {{
        "value_column": "Transport",
        "label_column": "{entity_col}",
        "reference_period": "{recommended_year}",
        "n": 10,
        "mode": "top",
        "exclude_aggregates": true
      }},
      "reference_period": "{recommended_year}",
      "why": "제안 이유 설명",
      "caution": "주의사항 설명"
    }}
  ]
}}
"""

    logger.info(f'[AI] suggest 요청 시작 (model={GEMINI_MODEL})')
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                'response_mime_type': 'application/json'
            }
        )
        response_text = response.text or ''
        logger.info(f'[AI] suggest 응답 수신 길이: {len(response_text)} chars')

        try:
            clean_text = response_text.strip()
            if clean_text.startswith('```json'):
                clean_text = clean_text[7:]
            if clean_text.startswith('```'):
                clean_text = clean_text[3:]
            if clean_text.endswith('```'):
                clean_text = clean_text[:-3]

            parsed_json = json.loads(clean_text.strip())
            suggestions = parsed_json.get('suggestions', [])
            logger.info(f'[AI] JSON 파싱 완료. 제안 개수: {len(suggestions)}')
        except Exception as parse_err:
            logger.error(f'[ERROR] Gemini 응답 JSON 파싱 실패: {parse_err}')
            return jsonify({'error': 'AI 응답을 JSON으로 변환하는 데 실패했습니다.', 'raw': response_text}), 502

        valid_suggestions = []
        for s in suggestions:
            tool_name = s.get('tool')
            if tool_name not in TOOL_FUNCTION_MAP:
                logger.warning(f'[AI] 카탈로그에 없는 도구 제안 제외: {tool_name}')
                continue
            params = s.get('params', {})
            invalid_col = False
            for col_key in ['value_column', 'sector_column', 'x_column', 'y_column']:
                if col_key in params:
                    col_val = params[col_key]
                    if col_val not in emission_sectors and col_val not in meta.get('column_names', []):
                        invalid_col = True
                        break
            if invalid_col:
                logger.warning(f'[AI] 데이터셋에 없는 열을 포함한 제안 제외: {params}')
                continue

            valid_suggestions.append(s)

        if len(valid_suggestions) < 3:
            first_sec = emission_sectors[0] if emission_sectors else "Transport"
            second_sec = emission_sectors[1] if len(emission_sectors) > 1 else first_sec
            valid_suggestions.append({
                "tool": "top_bottom_n",
                "params": {"value_column": first_sec, "label_column": entity_col, "reference_period": recommended_year, "n": 10, "mode": "top", "exclude_aggregates": True},
                "reference_period": recommended_year,
                "why": f"{recommended_year}년 기준 {first_sec} 부문의 주요 배출 국가 순위를 파악할 수 있습니다.",
                "caution": "순위 왜곡을 막기 위해 대륙 및 전세계 집계 행은 제외됩니다."
            })
            valid_suggestions.append({
                "tool": "group_summary",
                "params": {"reference_period": recommended_year, "exclude_aggregates": True},
                "reference_period": recommended_year,
                "why": f"{recommended_year}년도 전체 온실가스 중 어느 부문의 배출량이 가장 큰지 비교할 수 있습니다.",
                "caution": "결측 국가가 있는 경우 해당 국가는 0이 아닌 집계 제외 처리됩니다."
            })
            valid_suggestions.append({
                "tool": "correlation_scatter",
                "params": {"x_column": first_sec, "y_column": second_sec, "reference_period": recommended_year, "exclude_aggregates": True},
                "reference_period": recommended_year,
                "why": f"{first_sec} 부문과 {second_sec} 부문 배출량 사이의 상관관계를 탐색합니다.",
                "caution": "상관관계는 인과관계가 아닙니다. 두 부문이 함께 증가한다고 해서 원인과 결과는 아닙니다."
            })

        final_response = {
            "model": GEMINI_MODEL,
            "suggestions": valid_suggestions[:5]
        }
        logger.info(f'[RESPONSE] status=200 최종 유효 제안 {len(final_response["suggestions"])}건 반환')
        return jsonify(sanitize_for_json(final_response)), 200

    except Exception as e:
        logger.error(f'[ERROR] Gemini API 호출 실패: {str(e)}', exc_info=True)
        return jsonify({'error': f'Gemini API 호출 중 오류가 발생했습니다: {str(e)}'}), 500

@app.route('/run', methods=['POST'])
def run_analysis():
    """선택된 도구를 Pandas로 직접 실행하여 수치 계산 결과 및 차트 데이터 반환"""
    logger.info('[REQUEST] POST /run')

    if CURRENT_DATASET['df'] is None:
        logger.error('[ERROR] 메모리에 데이터셋이 없습니다.')
        return jsonify({'error': '분석할 데이터가 없습니다. 먼저 CSV 파일을 업로드해 주세요.'}), 400

    req_data = request.get_json(silent=True) or {}
    tool_name = req_data.get('tool')
    params = req_data.get('params', {})

    if not tool_name:
        logger.error('[ERROR] 도구명이 지정되지 않았습니다.')
        return jsonify({'error': '실행할 도구명(tool)을 지정해 주세요.'}), 400

    if tool_name not in TOOL_FUNCTION_MAP:
        logger.error(f'[ERROR] 도구 카탈로그에 없는 도구 요청: {tool_name}')
        return jsonify({'error': f"'{tool_name}'은(는) 지원하지 않는 분석 도구입니다. 카탈로그에 등록된 도구만 실행 가능합니다."}), 400

    tools_requiring_period = {
        'top_bottom_n', 'group_summary', 'distribution', 'correlation_scatter', 'compare_one_vs_all'
    }
    if tool_name in tools_requiring_period:
        ref_period = params.get('reference_period')
        if not ref_period:
            logger.error(f'[ERROR] {tool_name} 실행 시 필수 기준시점 누락')
            return jsonify({'error': f"'{tool_name}' 도구를 실행하려면 기준 시점(reference_period, 예: 2023)을 필수로 입력해야 합니다."}), 400

    if tool_name == 'change_rate':
        if not params.get('start_period') or not params.get('end_period'):
            logger.error('[ERROR] change_rate 실행 시 시작/종료 시점 누락')
            return jsonify({'error': "'change_rate' 도구는 시작 시점(start_period)과 종료 시점(end_period)이 모두 필요합니다."}), 400

    target_func = TOOL_FUNCTION_MAP[tool_name]
    df = CURRENT_DATASET['df']

    try:
        result = target_func(df, **params)
    except TypeError as te:
        logger.error(f'[ERROR] 잘못된 파라미터 전달: {te}')
        return jsonify({'error': f"도구 실행 파라미터가 올바르지 않습니다: {str(te)}"}), 400
    except ValueError as ve:
        logger.error(f'[ERROR] 도구 실행 중 검증 오류: {ve}')
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f'[ERROR] 도구 실행 중 예기치 않은 오류 발생: {e}', exc_info=True)
        return jsonify({'error': f"분석 계산 중 오류가 발생했습니다: {str(e)}"}), 500

    used_rows = result.get('used_rows', 0)
    excluded_rows = result.get('excluded_rows', 0)
    logger.info(f'[TOOL] 도구={tool_name}, 파라미터={params}, 사용 행 수={used_rows}, 제외 행 수={excluded_rows}')

    CURRENT_DATASET['last_run_result'] = {
        'tool': tool_name,
        'params': params,
        'result': result
    }

    logger.info(f'[RESPONSE] status=200 tool={tool_name} 계산 완료')
    return jsonify(sanitize_for_json(result)), 200

@app.route('/explain', methods=['POST'])
def explain_result():
    """/run의 계산 결과만 Gemini에 전달하여 해석 생성 (모드 A/B)"""
    logger.info('[REQUEST] POST /explain')

    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not api_key or api_key == 'your_gemini_api_key_here':
        logger.error('[ERROR] API Key가 설정되지 않았습니다.')
        return jsonify({'error': 'Gemini API Key가 설정되지 않았습니다. .env 파일에 올바른 키를 입력해 주세요.'}), 401

    req_data = request.get_json(silent=True) or {}
    mode = str(req_data.get('mode', 'B')).strip().upper()
    if mode not in ['A', 'B']:
        mode = 'B'

    run_result = req_data.get('result')
    if not run_result and CURRENT_DATASET.get('last_run_result'):
        run_result = CURRENT_DATASET['last_run_result'].get('result')

    if not run_result and mode == 'B':
        logger.error('[ERROR] /explain 실행을 위한 계산 결과가 없습니다.')
        return jsonify({'error': '해석할 분석 계산 결과가 없습니다. 먼저 도구를 실행(/run)해 주세요.'}), 400

    meta = CURRENT_DATASET.get('meta') or {}
    logger.info(f'[AI] explain 요청 시작 (모드 {mode}, model={GEMINI_MODEL})')

    if mode == 'A':
        prompt = f"""
이 온실가스 데이터 파일을 분석해서 보고서를 작성해줘.
파일명: {meta.get('filename', '온실가스 배출량 데이터')}
열 목록: {', '.join(meta.get('column_names', []))}
총 행 수: {meta.get('rows', '수천 행')}
"""
    else:
        calculation_payload = {
            "tool": run_result.get('tool'),
            "reference_period": run_result.get('reference_period'),
            "used_rows": run_result.get('used_rows'),
            "excluded_rows": run_result.get('excluded_rows'),
            "exclusion_reason": run_result.get('exclusion_reason'),
            "used_columns": run_result.get('used_columns'),
            "unit": run_result.get('unit'),
            "caution": run_result.get('caution'),
            "calculated_data": run_result.get('data')
        }

        prompt = f"""
당신은 온실가스 배출량 데이터 전문 과학 분석가입니다.
아래 제공된 'Pandas 계산 결과'를 바탕으로 객관적이고 신뢰할 수 있는 해석 보고서를 작성하세요.

[준수해야 할 8대 절대 규칙]
1. 반드시 아래 제공된 'Pandas 계산 결과'에 실제로 존재하는 숫자만 사용하세요.
2. 절대로 직접 새로운 숫자를 암산, 계산하거나 추정하지 마세요.
3. 데이터에 없는 국가, 연도, 배출 부문을 임의로 언급하지 마세요.
4. 기준 시점('{run_result.get('reference_period')}')과 제외된 행 수({run_result.get('excluded_rows')}행) 및 제외 이유를 본문에 반드시 명시하세요.
5. 상관관계를 인과관계로 표현하지 마세요.
6. 온실가스 부문별 배출 지표의 정의(tCO2e)와 데이터 출처(Our World in Data)를 보고서 앞부분에 명기하세요.
7. 확인할 수 없는 것은 "이 데이터로는 확인할 수 없다"라고 솔직하게 쓰세요.
8. 중학생도 흥미롭게 이해할 수 있도록 친절하고 명쾌하게 서술하세요.

[제공된 Pandas 계산 결과]
{json.dumps(calculation_payload, ensure_ascii=False, indent=2)}

[출력 형식 - 반드시 아래 7개 마크다운 헤더를 그대로 사용할 것]
## 무엇을 봤는가
## 데이터 출처와 정의 (온실가스 부문별 배출량)
## 기준 시점과 제외된 항목
## 계산 결과
## 읽어낼 수 있는 것
## 이 데이터로는 알 수 없는 것
## 다음에 확인해볼 것
"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        explanation_text = response.text or ''
        logger.info(f'[AI] explain 응답 수신 완료 (길이: {len(explanation_text)} chars)')

        CURRENT_DATASET['last_explanation'] = explanation_text

        response_data = {
            "mode": mode,
            "model": GEMINI_MODEL,
            "tool": run_result.get('tool') if run_result else 'overview',
            "explanation": explanation_text
        }
        logger.info(f'[RESPONSE] status=200 mode={mode} 해석 반환')
        return jsonify(sanitize_for_json(response_data)), 200

    except Exception as e:
        logger.error(f'[ERROR] Gemini explain 호출 실패: {str(e)}', exc_info=True)
        return jsonify({'error': f'해석 생성 중 오류가 발생했습니다: {str(e)}'}), 500

def preload_sample_dataset():
    """서버 구동 시 공식 온실가스 CSV를 메모리에 자동 사전 탑재하여 다른 컴퓨터에서 접속 시 즉시 사용 가능하게 함"""
    sample_path = os.path.join(os.path.dirname(__file__), 'data', 'ghg-emissions-by-sector.csv')
    if os.path.exists(sample_path):
        try:
            with open(sample_path, 'rb') as f:
                raw_bytes = f.read()
            df, enc, skipped = detect_header_and_read(raw_bytes)
            cols = [str(c).strip() for c in df.columns]
            df.columns = cols
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            sec_cols = [c for c in num_cols if c != 'Year']

            year_counts = df['Year'].dropna().value_counts().sort_index()
            year_cov = {str(int(k)): int(v) for k, v in year_counts.items()}

            CURRENT_DATASET['df'] = df
            CURRENT_DATASET['meta'] = {
                'filename': 'ghg-emissions-by-sector.csv',
                'file_size_bytes': len(raw_bytes),
                'encoding': enc,
                'skipped_rows': skipped,
                'rows': len(df),
                'columns': len(cols),
                'column_names': cols,
                'numeric_columns': num_cols,
                'string_columns': df.select_dtypes(exclude=[np.number]).columns.tolist(),
                'year_col': 'Year',
                'entity_col': 'Entity',
                'code_col': 'Code' if 'Code' in cols else None,
                'emission_sectors': sec_cols,
                'recommended_year': '2023',
                'year_coverage': year_cov
            }
            logger.info('공식 온실가스 데이터셋(6,969행) 메모리 사전 탑재 완료!')
        except Exception as e:
            logger.warning(f'데이터셋 사전 탑재 실패: {e}')

if __name__ == '__main__':
    preload_sample_dataset()
    logger.info('Starting Flask development server on 0.0.0.0:5000 (모든 네트워크 접속 허용)...')
    app.run(host='0.0.0.0', port=5000, debug=FLASK_DEBUG)
