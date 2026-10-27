import math
import re
import numpy as np
import pandas as pd

# 온실가스 배출 부문 한국어 번역 사전
SECTOR_KO_MAP = {
    "Electricity and heat": "전기 및 열 생산 (발전소)",
    "Transport": "수송 (교통/차량/항공)",
    "Manufacturing and construction": "제조 및 건설업",
    "Agriculture": "농업",
    "Industry": "산업 공정",
    "Buildings": "건물 (상업/주거 냉난방)",
    "Waste": "폐기물 처리",
    "Fugitive emissions": "탈루 배출 (에너지 채굴/누출)",
    "Land-use change and forestry": "산림 및 토지이용 (흡수원)",
    "Other fuel combustion": "기타 연료 연소",
    "Aviation and shipping": "국제 항공 및 해운"
}

# 주요 국가 한국어 번역 사전
COUNTRY_KO_MAP = {
    "China": "중국",
    "United States": "미국",
    "India": "인도",
    "Russia": "러시아",
    "Brazil": "브라질",
    "Indonesia": "인도네시아",
    "Japan": "일본",
    "Iran": "이란",
    "Germany": "독일",
    "Saudi Arabia": "사우디아라비아",
    "South Korea": "대한민국",
    "Canada": "캐나다",
    "Mexico": "멕시코",
    "South Africa": "남아프리카공화국",
    "Australia": "호주",
    "Turkey": "튀르키예",
    "United Kingdom": "영국",
    "Vietnam": "베트남",
    "Italy": "이탈리아",
    "France": "프랑스",
    "Poland": "폴란드",
    "Thailand": "태국",
    "Egypt": "이집트",
    "Pakistan": "파키스탄",
    "Malaysia": "말레이시아",
    "Argentina": "아르헨티나",
    "Spain": "스페인",
    "Kazakhstan": "카자흐스탄",
    "Philippines": "필리핀",
    "Nigeria": "나이지리아",
    "World": "전 세계"
}

def ko_sector(sec):
    """부문명을 친절한 한국어로 변환"""
    return SECTOR_KO_MAP.get(str(sec).strip(), str(sec))

def ko_country(country, with_eng=True):
    """국가명을 한국어로 변환 (기본값: 한국어 (영문) 병기)"""
    c_str = str(country).strip()
    if c_str in COUNTRY_KO_MAP:
        return f"{COUNTRY_KO_MAP[c_str]} ({c_str})" if with_eng else COUNTRY_KO_MAP[c_str]
    return c_str

# 집계명 식별 상수
EXACT_AGGREGATE_ENTITIES = {
    'world', 'africa', 'asia', 'europe', 'oceania', 'north america', 'south america',
    'european union (27)', 'european union (28)', 'european union',
    'high-income countries', 'low-income countries', 'lower-middle-income countries',
    'upper-middle-income countries', 'oecd members', 'euro area'
}

AGGREGATE_PATTERNS = [
    r'\bworld\b', r'\boecd\b', r'\beuro area\b', r'\beuropean union\b',
    r'\bincome countries\b', r'\bglobal total\b', r'\bsector total\b'
]

def sanitize_value(val):
    """NaN, Infinity, numpy 타입을 JSON 직렬화 가능한 순수 파이썬 타입으로 변환"""
    if isinstance(val, (float, np.floating)):
        if math.isnan(val) or math.isinf(val):
            return None
        return round(float(val), 4)
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if isinstance(val, dict):
        return {k: sanitize_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [sanitize_value(v) for v in val]
    if pd.isna(val):
        return None
    return val

def is_aggregate_row(entity_val, code_val=None):
    """개별 국가가 아닌 전세계/대륙/소득군 집계 행인지 판별"""
    ent_lower = str(entity_val).strip().lower()
    if ent_lower in EXACT_AGGREGATE_ENTITIES:
        return True
    for pat in AGGREGATE_PATTERNS:
        if re.search(pat, ent_lower):
            return True
    if code_val is not None and pd.notna(code_val):
        code_str = str(code_val).strip()
        if code_str.startswith('OWID_'):
            return True
    return False

def filter_aggregates_if_needed(df, exclude_aggregates=True, entity_col=None, code_col=None):
    """집계 행 제외 옵션에 따라 필터링 수행"""
    total_rows = len(df)
    if not exclude_aggregates:
        return df.copy(), 0, "집계 행을 제외하지 않고 모두 포함함"

    if not entity_col:
        for col in df.columns:
            if any(k in col.lower() for k in ['entity', 'country', 'nation', '국가']):
                entity_col = col
                break

    if not code_col:
        for col in df.columns:
            if any(k in col.lower() for k in ['code', 'iso', '코드']):
                code_col = col
                break

    if not entity_col or entity_col not in df.columns:
        return df.copy(), 0, "국가/개체 식별 열이 없어 집계 행을 필터링하지 못함"

    agg_mask = df.apply(
        lambda r: is_aggregate_row(r[entity_col], r[code_col] if code_col and code_col in df.columns else None),
        axis=1
    )
    excluded_count = int(agg_mask.sum())
    filtered_df = df[~agg_mask].copy()

    reason = f"전 세계/대륙/소득군 집계 행({excluded_count}건)을 국가 간 왜곡 없는 비교를 위해 제외함" if excluded_count > 0 else "제외 대상 집계 행 없음"
    return filtered_df, excluded_count, reason

def get_year_col(df):
    """연도 열 이름 자동 감지"""
    for col in df.columns:
        if any(k in col.lower() for k in ['year', '연도', 'date', 'yr']):
            return col
    return None

def get_entity_col(df):
    """국가/개체 식별 열 이름 자동 감지"""
    for col in df.columns:
        if any(k in col.lower() for k in ['entity', 'country', 'nation', '국가']):
            return col
    return None

# ==========================================================
# 1. reshape_wide_to_long
# ==========================================================
def reshape_wide_to_long(df, id_vars=None, value_vars=None, var_name='Sector', value_name='Emissions'):
    total_rows = len(df)
    if id_vars is None:
        id_vars = [c for c in df.columns if any(k in c.lower() for k in ['entity', 'country', 'code', 'year', 'date', '연도', '국가'])]
    if value_vars is None:
        value_vars = [c for c in df.columns if c not in id_vars and pd.api.types.is_numeric_dtype(df[c])]

    melted_df = pd.melt(
        df,
        id_vars=id_vars,
        value_vars=value_vars,
        var_name=var_name,
        value_name=value_name
    )
    sample_preview = melted_df.head(10).replace({np.nan: None}).to_dict(orient='records')

    return sanitize_value({
        "tool": "reshape_wide_to_long",
        "reference_period": "전체 시계열",
        "used_rows": total_rows,
        "excluded_rows": 0,
        "exclusion_reason": "전체 행 대상 포맷 변환 수행",
        "used_columns": id_vars + value_vars,
        "unit": "온실가스 배출량 (tCO2e 원본 단위)",
        "caution": "열이 행으로 변환되면서 총 행 수가 (원본 행 수 × 부문 수)로 증가합니다.",
        "data": {
            "original_rows": total_rows,
            "transformed_rows": len(melted_df),
            "id_columns": id_vars,
            "melted_sector_columns": value_vars,
            "preview": sample_preview
        },
        "chart": None
    })

# ==========================================================
# 2. quality_report
# ==========================================================
def quality_report(df):
    total_rows = len(df)
    used_columns = list(df.columns)

    missing_stats = {}
    for col in df.columns:
        cnt = int(df[col].isna().sum())
        missing_stats[ko_sector(col)] = {
            "missing_count": cnt,
            "missing_pct": round((cnt / total_rows) * 100, 2) if total_rows > 0 else 0
        }

    duplicate_rows = int(df.duplicated().sum())

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    negative_values = {}
    for col in numeric_cols:
        neg_cnt = int((df[col] < 0).sum())
        if neg_cnt > 0:
            negative_values[ko_sector(col)] = neg_cnt

    unnamed_cols = [c for c in df.columns if 'unnamed' in c.lower() or not str(c).strip()]
    empty_cols = [c for c in df.columns if df[c].isna().all()]

    return sanitize_value({
        "tool": "quality_report",
        "reference_period": "전체 데이터",
        "used_rows": total_rows,
        "excluded_rows": 0,
        "exclusion_reason": "전체 데이터셋 대상 품질 평가",
        "used_columns": used_columns,
        "unit": "건수 및 비율(%)",
        "caution": "토지이용 및 산림(LULUCF) 부문 배출량은 탄소 흡수원으로 인해 음수(-)가 나타날 수 있습니다.",
        "data": {
            "total_rows": total_rows,
            "total_columns": len(used_columns),
            "duplicate_rows": duplicate_rows,
            "missing_stats": missing_stats,
            "negative_emission_counts": negative_values,
            "unnamed_columns": unnamed_cols,
            "empty_columns": empty_cols
        },
        "chart": {
            "type": "bar",
            "title": "열별 결측치 비율 (%)",
            "labels": list(missing_stats.keys()),
            "datasets": [{
                "label": "결측치 비율 (%)",
                "data": [missing_stats[c]["missing_pct"] for c in missing_stats.keys()]
            }]
        }
    })

# ==========================================================
# 3. year_coverage
# ==========================================================
def year_coverage(df, year_column=None):
    if not year_column:
        year_column = get_year_col(df)

    if not year_column or year_column not in df.columns:
        raise ValueError("연도(Year) 열을 찾을 수 없습니다.")

    year_counts = df[year_column].dropna().value_counts().sort_index()
    coverage_dict = {str(int(k) if isinstance(k, (int, float, np.integer, np.floating)) else k): int(v) 
                     for k, v in year_counts.items()}

    max_count = max(coverage_dict.values()) if coverage_dict else 0
    valid_years = [y for y, c in coverage_dict.items() if c >= max_count * 0.8]
    try:
        recommended_year = str(max(int(y) for y in valid_years)) if valid_years else None
    except ValueError:
        recommended_year = str(valid_years[-1]) if valid_years else None

    int_years = []
    for y in coverage_dict.keys():
        try:
            int_years.append(int(y))
        except ValueError:
            pass

    return sanitize_value({
        "tool": "year_coverage",
        "reference_period": f"{min(int_years)}년 ~ {max(int_years)}년" if int_years else "전체",
        "used_rows": int(df[year_column].notna().sum()),
        "excluded_rows": int(df[year_column].isna().sum()),
        "exclusion_reason": "연도 값이 없는 결측 행 제외",
        "used_columns": [year_column],
        "unit": "연도별 수집 국가 수",
        "caution": "연도별로 보고 국가 수가 다를 수 있으므로 단일 시점 분석 시 권장 기준연도를 우선 고려해야 합니다.",
        "data": {
            "year_column": year_column,
            "min_year": min(int_years) if int_years else None,
            "max_year": max(int_years) if int_years else None,
            "recommended_year": recommended_year,
            "coverage_by_year": coverage_dict
        },
        "chart": {
            "type": "line",
            "title": "연도별 수집 국가/개체 수 추이 (1990~2023)",
            "labels": [f"{y}년" for y in coverage_dict.keys()],
            "datasets": [{
                "label": "보고 국가 수 (개국)",
                "data": list(coverage_dict.values())
            }]
        }
    })

# ==========================================================
# 4. detect_aggregates
# ==========================================================
def detect_aggregates(df, entity_column=None, code_column=None):
    total_rows = len(df)
    if not entity_column:
        entity_column = get_entity_col(df)
    if not code_column:
        for col in df.columns:
            if any(k in col.lower() for k in ['code', 'iso', '코드']):
                code_column = col
                break

    if not entity_column or entity_column not in df.columns:
        raise ValueError("국가/개체(Entity) 열을 찾을 수 없습니다.")

    agg_mask = df.apply(
        lambda r: is_aggregate_row(r[entity_column], r[code_column] if code_column and code_column in df.columns else None),
        axis=1
    )

    agg_count = int(agg_mask.sum())
    agg_entities = df.loc[agg_mask, entity_column].dropna().unique().tolist()
    pure_country_entities = df.loc[~agg_mask, entity_column].dropna().unique().tolist()

    return sanitize_value({
        "tool": "detect_aggregates",
        "reference_period": "전체 데이터셋",
        "used_rows": total_rows,
        "excluded_rows": 0,
        "exclusion_reason": "전체 행 대상 집계 행 분포 분석",
        "used_columns": [c for c in [entity_column, code_column] if c],
        "unit": "행 수 및 개체 수",
        "caution": "국가별 순위 및 비교 분석 시 이 집계 행들을 제외하지 않으면 상위 순위가 대륙 및 전세계 총합으로 왜곡됩니다.",
        "data": {
            "total_rows": total_rows,
            "aggregate_rows_count": agg_count,
            "pure_country_rows_count": total_rows - agg_count,
            "aggregate_entities_count": len(agg_entities),
            "pure_countries_count": len(pure_country_entities),
            "aggregate_entities_list": agg_entities,
            "sample_pure_countries": [ko_country(c) for c in pure_country_entities[:15]]
        },
        "chart": {
            "type": "pie",
            "title": "순수 개별 국가 vs 대륙/전세계 집계 덩어리 비중",
            "labels": ["순수 개별 국가 (193개국)", "대륙/소득군/전세계 집계 행 (408건)"],
            "datasets": [{
                "data": [total_rows - agg_count, agg_count]
            }]
        }
    })

# ==========================================================
# 5. describe_numeric
# ==========================================================
def describe_numeric(df, value_columns=None, reference_period=None, exclude_aggregates=True):
    total_original_rows = len(df)
    work_df = df.copy()
    excluded_reasons = []
    total_excluded = 0

    year_col = get_year_col(work_df)
    if reference_period and year_col and year_col in work_df.columns:
        pre_cnt = len(work_df)
        work_df = work_df[work_df[year_col].astype(str) == str(reference_period)]
        diff = pre_cnt - len(work_df)
        if diff > 0:
            total_excluded += diff
            excluded_reasons.append(f"기준시점({reference_period}년) 외 {diff}개 행 제외")
        ref_text = f"{reference_period}년"
    else:
        ref_text = "전체 시계열"

    work_df, agg_exc, agg_reason = filter_aggregates_if_needed(work_df, exclude_aggregates=exclude_aggregates)
    if agg_exc > 0:
        total_excluded += agg_exc
        excluded_reasons.append(agg_reason)

    if value_columns is None:
        value_columns = work_df.select_dtypes(include=[np.number]).columns.tolist()
        if year_col and year_col in value_columns:
            value_columns.remove(year_col)

    stats = {}
    chart_labels = []
    means = []
    medians = []

    for col in value_columns:
        s = work_df[col].dropna()
        if s.empty:
            continue
        ko_name = ko_sector(col)
        mean_v = float(s.mean())
        median_v = float(s.median())
        stats[ko_name] = {
            "count": int(s.count()),
            "mean": mean_v,
            "median": median_v,
            "std": float(s.std()) if len(s) > 1 else 0.0,
            "min": float(s.min()),
            "max": float(s.max()),
            "q25": float(s.quantile(0.25)),
            "q75": float(s.quantile(0.75))
        }
        chart_labels.append(ko_name)
        means.append(mean_v)
        medians.append(median_v)

    return sanitize_value({
        "tool": "describe_numeric",
        "reference_period": ref_text,
        "used_rows": len(work_df),
        "excluded_rows": total_excluded,
        "exclusion_reason": "; ".join(excluded_reasons) if excluded_reasons else "제외된 행 없음",
        "used_columns": value_columns,
        "unit": "tCO2e (톤 CO2 환산량)",
        "caution": "국가별 배출 규모 차이가 극심하므로 평균값(Mean)보다 중앙값(Median)이 일반적인 국가 수준을 더 잘 반영합니다.",
        "data": stats,
        "chart": {
            "type": "bar",
            "title": f"{ref_text} 온실가스 부문별 평균 및 중앙값 비교",
            "labels": chart_labels,
            "datasets": [
                {"label": "평균 배출량 (Mean)", "data": means},
                {"label": "중앙값 배출량 (Median)", "data": medians}
            ]
        }
    })

# ==========================================================
# 6. trend_line
# ==========================================================
def trend_line(df, entities=None, sectors=None, entity_col=None, year_col=None, exclude_aggregates=False):
    total_original_rows = len(df)
    if not year_col:
        year_col = get_year_col(df)
    if not entity_col:
        entity_col = get_entity_col(df)

    if not year_col or year_col not in df.columns:
        raise ValueError("시계열 분석을 위한 연도(Year) 열을 찾을 수 없습니다.")

    work_df = df.copy()
    excluded_reasons = []
    total_excluded = 0

    null_years = int(work_df[year_col].isna().sum())
    if null_years > 0:
        work_df = work_df[work_df[year_col].notna()]
        total_excluded += null_years
        excluded_reasons.append(f"연도 결측치 {null_years}행 제외")

    work_df, agg_exc, agg_reason = filter_aggregates_if_needed(work_df, exclude_aggregates=exclude_aggregates, entity_col=entity_col)
    if agg_exc > 0:
        total_excluded += agg_exc
        excluded_reasons.append(agg_reason)

    all_num_cols = work_df.select_dtypes(include=[np.number]).columns.tolist()
    if year_col in all_num_cols:
        all_num_cols.remove(year_col)

    if not sectors:
        sectors = [all_num_cols[0]] if all_num_cols else []

    if not entities and entity_col and entity_col in work_df.columns:
        avail_entities = work_df[entity_col].dropna().unique().tolist()
        priority_candidates = ['World', 'China', 'United States', 'India', 'South Korea', 'Germany']
        entities = [e for e in priority_candidates if e in avail_entities]
        if not entities:
            entities = avail_entities[:3]

    years = sorted(list(set(int(y) for y in work_df[year_col].dropna().unique())))
    years_str = [f"{y}년" for y in years]

    datasets = []
    trend_data = {}

    for ent in entities:
        ent_df = work_df[work_df[entity_col].astype(str) == str(ent)].copy()
        ent_df_indexed = ent_df.set_index(ent_df[year_col].astype(int))
        ent_ko = ko_country(ent)
        for sec in sectors:
            if sec not in work_df.columns:
                continue
            sec_ko = ko_sector(sec)
            series_label = f"{ent_ko} - {sec_ko}" if len(sectors) > 1 else ent_ko
            series_vals = []
            for y in years:
                if y in ent_df_indexed.index:
                    val = ent_df_indexed.loc[y, sec]
                    if isinstance(val, pd.Series):
                        val = val.iloc[0]
                    series_vals.append(float(val) if pd.notna(val) else None)
                else:
                    series_vals.append(None)

            datasets.append({
                "label": series_label,
                "data": [sanitize_value(v) for v in series_vals]
            })
            trend_data[series_label] = dict(zip(years_str, [sanitize_value(v) for v in series_vals]))

    used_rows = len(work_df[work_df[entity_col].astype(str).isin([str(e) for e in entities])]) if entity_col else len(work_df)
    sec_names_ko = [ko_sector(s) for s in sectors]

    return sanitize_value({
        "tool": "trend_line",
        "reference_period": f"{min(years)}년 ~ {max(years)}년",
        "used_rows": used_rows,
        "excluded_rows": total_original_rows - used_rows,
        "exclusion_reason": f"선택한 엔티티({entities}) 외 행 및 필터링 행 제외",
        "used_columns": [year_col, entity_col] + sectors,
        "unit": "tCO2e (톤 CO2 환산량)",
        "caution": "시계열 중간에 특정 연도의 데이터가 누락되어 선이 단절될 수 있습니다.",
        "data": {
            "entities": [ko_country(e) for e in entities],
            "sectors": sec_names_ko,
            "years": years_str,
            "series": trend_data
        },
        "chart": {
            "type": "line",
            "title": f"온실가스 연도별 배출량 추이 ({', '.join(sec_names_ko)})",
            "labels": years_str,
            "datasets": datasets
        }
    })

# ==========================================================
# 7. top_bottom_n (기준시점 필수!)
# ==========================================================
def top_bottom_n(df, value_column, reference_period, n=10, mode='top', label_column=None, exclude_aggregates=True):
    if not reference_period:
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다. 연도를 지정해 주세요.")

    total_original_rows = len(df)
    year_col = get_year_col(df)
    if not year_col or year_col not in df.columns:
        raise ValueError("연도(Year) 열을 찾을 수 없어 기준시점 필터링이 불가합니다.")

    if not label_column:
        label_column = get_entity_col(df)
    if not label_column or label_column not in df.columns:
        raise ValueError("라벨(국가/개체) 열을 찾을 수 없습니다.")

    if value_column not in df.columns:
        raise ValueError(f"데이터셋에 '{value_column}' 열이 존재하지 않습니다.")

    excluded_reasons = []
    total_excluded = 0

    work_df = df[df[year_col].astype(str) == str(reference_period)].copy()
    diff_period = total_original_rows - len(work_df)
    total_excluded += diff_period
    excluded_reasons.append(f"기준시점({reference_period}년) 외 타 연도 {diff_period}행 제외")

    work_df, agg_exc, agg_reason = filter_aggregates_if_needed(work_df, exclude_aggregates=exclude_aggregates, entity_col=label_column)
    if agg_exc > 0:
        total_excluded += agg_exc
        excluded_reasons.append(agg_reason)

    null_val_cnt = int(work_df[value_column].isna().sum())
    if null_val_cnt > 0:
        work_df = work_df[work_df[value_column].notna()]
        total_excluded += null_val_cnt
        excluded_reasons.append(f"기준시점에 '{ko_sector(value_column)}' 값이 없는 결측 행 {null_val_cnt}건 제외")

    if work_df.empty:
        raise ValueError(f"{reference_period}년도에 '{value_column}'의 유효한 데이터가 존재하지 않습니다.")

    ascending = (mode.lower() == 'bottom')
    sorted_df = work_df.sort_values(by=value_column, ascending=ascending).head(int(n))

    # 한국(South Korea)이 상위 N개에 포함되지 않았을 경우, 사용자 비교를 위해 하단에 강조 병기
    has_korea = sorted_df[label_column].astype(str).str.lower().eq('south korea').any()
    korea_row = work_df[work_df[label_column].astype(str).str.lower().eq('south korea')]
    
    labels = [ko_country(c) for c in sorted_df[label_column].astype(str).tolist()]
    values = sorted_df[value_column].tolist()

    rank_data = [
        {"rank": idx + 1, "label": lbl, "value": sanitize_value(val)}
        for idx, (lbl, val) in enumerate(zip(labels, values))
    ]

    if not has_korea and not korea_row.empty and not ascending:
        k_val = float(korea_row[value_column].iloc[0])
        # 전체 중 순위 계산
        k_rank = int((work_df[value_column] > k_val).sum()) + 1
        labels.append(f"★ 대한민국 (South Korea, 전체 {k_rank}위)")
        values.append(k_val)
        rank_data.append({"rank": k_rank, "label": f"★ 대한민국 (South Korea, 전체 {k_rank}위)", "value": sanitize_value(k_val)})

    mode_text = "상위" if not ascending else "하위"
    sector_ko = ko_sector(value_column)

    return sanitize_value({
        "tool": "top_bottom_n",
        "reference_period": f"{reference_period}년",
        "used_rows": len(work_df),
        "excluded_rows": total_excluded,
        "exclusion_reason": "; ".join(excluded_reasons),
        "used_columns": [year_col, label_column, value_column],
        "unit": "tCO2e (톤 CO2 환산량)",
        "caution": f"집계 행({'제외됨' if exclude_aggregates else '포함됨'}) 상태이며, 인구 규모에 따른 배출량 차이가 고려되지 않은 국가별 절대 배출량입니다.",
        "data": {
            "mode": mode_text,
            "n": int(n),
            "value_column": sector_ko,
            "ranking": rank_data
        },
        "chart": {
            "type": "bar",
            "indexAxis": "y",
            "title": f"{reference_period}년 {sector_ko} 배출량 {mode_text} {n}개국 순위 비교",
            "labels": labels,
            "datasets": [{
                "label": f"{sector_ko} 배출량 (tCO2e)",
                "data": [sanitize_value(v) for v in values]
            }]
        }
    })

# ==========================================================
# 8. group_summary (기준시점 필수!)
# ==========================================================
def group_summary(df, group_by_column=None, value_column=None, reference_period=None, exclude_aggregates=True):
    if not reference_period:
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다. 연도를 지정해 주세요.")

    total_original_rows = len(df)
    year_col = get_year_col(df)
    if not year_col or year_col not in df.columns:
        raise ValueError("연도(Year) 열을 찾을 수 없어 기준시점 필터링이 불가합니다.")

    excluded_reasons = []
    total_excluded = 0

    work_df = df[df[year_col].astype(str) == str(reference_period)].copy()
    diff_period = total_original_rows - len(work_df)
    total_excluded += diff_period
    excluded_reasons.append(f"기준시점({reference_period}년) 외 {diff_period}행 제외")

    work_df, agg_exc, agg_reason = filter_aggregates_if_needed(work_df, exclude_aggregates=exclude_aggregates)
    if agg_exc > 0:
        total_excluded += agg_exc
        excluded_reasons.append(agg_reason)

    if work_df.empty:
        raise ValueError(f"{reference_period}년도에 유효한 데이터가 존재하지 않습니다.")

    if not group_by_column or group_by_column.lower() in ['sector', '부문']:
        num_cols = work_df.select_dtypes(include=[np.number]).columns.tolist()
        if year_col in num_cols:
            num_cols.remove(year_col)

        summary_rows = []
        for col in num_cols:
            s = work_df[col].dropna()
            if s.empty:
                continue
            summary_rows.append({
                "group": ko_sector(col),
                "sum": float(s.sum()),
                "mean": float(s.mean()),
                "median": float(s.median()),
                "count": int(s.count())
            })
        summary_rows.sort(key=lambda x: x["sum"], reverse=True)
        used_cols = [year_col] + num_cols
        labels = [r["group"] for r in summary_rows]
        sums = [r["sum"] for r in summary_rows]
    else:
        if not value_column:
            num_cols = work_df.select_dtypes(include=[np.number]).columns.tolist()
            if year_col in num_cols:
                num_cols.remove(year_col)
            value_column = num_cols[0]

        grouped = work_df.groupby(group_by_column)[value_column].agg(
            sum='sum', mean='mean', median='median', count='count'
        ).reset_index()
        grouped = grouped.sort_values(by='sum', ascending=False)
        summary_rows = grouped.to_dict(orient='records')
        used_cols = [year_col, group_by_column, value_column]
        labels = [ko_country(str(r[group_by_column])) for r in summary_rows]
        sums = [float(r["sum"]) for r in summary_rows]

    return sanitize_value({
        "tool": "group_summary",
        "reference_period": f"{reference_period}년",
        "used_rows": len(work_df),
        "excluded_rows": total_excluded,
        "exclusion_reason": "; ".join(excluded_reasons),
        "used_columns": used_cols,
        "unit": "tCO2e (톤 CO2 환산량)",
        "caution": "합계는 해당 그룹 내 국가들의 총 배출량이며, 보고되지 않은 결측 국가는 0으로 처리되지 않고 집계에서 제외되었습니다.",
        "data": {
            "reference_period": str(reference_period),
            "summary": summary_rows
        },
        "chart": {
            "type": "bar",
            "title": f"{reference_period}년 부문별 온실가스 총배출량 비교 (1위~11위)",
            "labels": labels,
            "datasets": [
                {"label": "전 세계 총배출량 합계 (tCO2e)", "data": [sanitize_value(s) for s in sums]}
            ]
        }
    })

# ==========================================================
# 9. change_rate
# ==========================================================
def change_rate(df, sector_column, start_period, end_period, label_column=None, n=10, exclude_aggregates=True):
    if not start_period or not end_period:
        raise ValueError("시작 시점(start_period)과 종료 시점(end_period)은 필수 파라미터입니다.")

    total_original_rows = len(df)
    year_col = get_year_col(df)
    if not label_column:
        label_column = get_entity_col(df)

    if not year_col or not label_column:
        raise ValueError("연도 열 또는 국가 식별 열을 찾을 수 없습니다.")

    if sector_column not in df.columns:
        raise ValueError(f"'{sector_column}' 열이 데이터셋에 존재하지 않습니다.")

    excluded_reasons = []
    total_excluded = 0

    work_df, agg_exc, agg_reason = filter_aggregates_if_needed(df, exclude_aggregates=exclude_aggregates, entity_col=label_column)
    if agg_exc > 0:
        total_excluded += agg_exc
        excluded_reasons.append(agg_reason)

    df_start = work_df[work_df[year_col].astype(str) == str(start_period)][[label_column, sector_column]].dropna()
    df_end = work_df[work_df[year_col].astype(str) == str(end_period)][[label_column, sector_column]].dropna()

    if df_start.empty or df_end.empty:
        raise ValueError(f"{start_period}년 또는 {end_period}년의 '{sector_column}' 데이터가 비어 있습니다.")

    merged = pd.merge(df_start, df_end, on=label_column, suffixes=('_start', '_end'))
    merged['abs_change'] = merged[f"{sector_column}_end"] - merged[f"{sector_column}_start"]
    merged['pct_change'] = np.where(
        merged[f"{sector_column}_start"] != 0,
        (merged['abs_change'] / merged[f"{sector_column}_start"].abs()) * 100,
        np.nan
    )

    merged = merged.dropna(subset=['pct_change'])
    merged = merged.sort_values(by='abs_change', ascending=False)
    top_increase = merged.head(int(n))

    labels = [ko_country(c) for c in top_increase[label_column].astype(str).tolist()]
    abs_vals = top_increase['abs_change'].tolist()

    rank_data = [
        {
            "entity": ko_country(str(r[label_column])),
            "start_val": float(r[f"{sector_column}_start"]),
            "end_val": float(r[f"{sector_column}_end"]),
            "abs_change": float(r['abs_change']),
            "pct_change": round(float(r['pct_change']), 2)
        }
        for _, r in top_increase.iterrows()
    ]

    used_rows = len(merged) * 2
    sec_ko = ko_sector(sector_column)

    return sanitize_value({
        "tool": "change_rate",
        "reference_period": f"{start_period}년 → {end_period}년",
        "used_rows": used_rows,
        "excluded_rows": total_original_rows - used_rows,
        "exclusion_reason": f"두 시점 모두에 데이터가 존재하는 국가({len(merged)}개국)만 매칭하여 계산함",
        "used_columns": [year_col, label_column, sector_column],
        "unit": "tCO2e (변화량), % (변화율)",
        "caution": "시작 연도의 배출량이 매우 적은 국가는 약간의 증가만으로도 변화율(%)이 극단적으로 높게 나타날 수 있습니다.",
        "data": {
            "sector": sec_ko,
            "start_period": str(start_period),
            "end_period": str(end_period),
            "evaluated_countries_count": len(merged),
            "top_increases": rank_data
        },
        "chart": {
            "type": "bar",
            "title": f"{start_period}~{end_period}년 {sec_ko} 배출량 증가 상위 {n}개국 (절대 변화량)",
            "labels": labels,
            "datasets": [
                {"label": "절대 증가량 (tCO2e)", "data": [sanitize_value(v) for v in abs_vals]}
            ]
        }
    })

# ==========================================================
# 10. distribution
# ==========================================================
def distribution(df, value_column, reference_period, bins=8, exclude_aggregates=True):
    if not reference_period:
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다. 연도를 지정해 주세요.")

    total_original_rows = len(df)
    year_col = get_year_col(df)
    entity_col = get_entity_col(df)

    if not year_col or not entity_col:
        raise ValueError("연도 열 또는 국가 식별 열을 찾을 수 없습니다.")

    if value_column not in df.columns:
        raise ValueError(f"'{value_column}' 열이 데이터셋에 존재하지 않습니다.")

    excluded_reasons = []
    total_excluded = 0

    work_df = df[df[year_col].astype(str) == str(reference_period)].copy()
    diff_period = total_original_rows - len(work_df)
    total_excluded += diff_period
    excluded_reasons.append(f"기준시점({reference_period}년) 외 {diff_period}행 제외")

    work_df, agg_exc, agg_reason = filter_aggregates_if_needed(work_df, exclude_aggregates=exclude_aggregates, entity_col=entity_col)
    if agg_exc > 0:
        total_excluded += agg_exc
        excluded_reasons.append(agg_reason)

    s = work_df[value_column].dropna()
    null_cnt = len(work_df) - len(s)
    if null_cnt > 0:
        total_excluded += null_cnt
        excluded_reasons.append(f"결측치 {null_cnt}행 제외")

    if s.empty:
        raise ValueError(f"{reference_period}년도에 '{value_column}' 데이터가 없습니다.")

    counts, bin_edges = np.histogram(s, bins=int(bins))
    bin_labels = []
    dist_items = []

    for i in range(len(counts)):
        low = bin_edges[i]
        high = bin_edges[i+1]
        lbl = f"{low:,.0f} ~ {high:,.0f}"
        bin_labels.append(lbl)
        in_bin_countries = work_df[(work_df[value_column] >= low) & (work_df[value_column] <= high)][entity_col].tolist()
        dist_items.append({
            "range": lbl,
            "min_val": float(low),
            "max_val": float(high),
            "count": int(counts[i]),
            "percentage": round(float(counts[i] / len(s) * 100), 2),
            "sample_countries": [ko_country(c) for c in in_bin_countries[:5]]
        })

    sec_ko = ko_sector(value_column)

    return sanitize_value({
        "tool": "distribution",
        "reference_period": f"{reference_period}년",
        "used_rows": len(s),
        "excluded_rows": total_excluded,
        "exclusion_reason": "; ".join(excluded_reasons),
        "used_columns": [year_col, entity_col, value_column],
        "unit": "국가 수 (건), tCO2e (구간)",
        "caution": "소수의 초대형 배출국으로 인해 대부분의 국가는 최하위 구간에 집중되는 극단적 비대칭(우측 꼬리) 분포를 띱니다.",
        "data": {
            "sector": sec_ko,
            "total_countries": len(s),
            "bins_count": int(bins),
            "distribution": dist_items
        },
        "chart": {
            "type": "bar",
            "title": f"{reference_period}년 {sec_ko} 배출량 구간별 국가 분포 (국가 수)",
            "labels": bin_labels,
            "datasets": [
                {"label": "해당 구간 국가 수 (개국)", "data": [int(c) for c in counts]}
            ]
        }
    })

# ==========================================================
# 11. correlation_scatter
# ==========================================================
def correlation_scatter(df, x_column, y_column, reference_period, label_column=None, exclude_aggregates=True):
    if not reference_period:
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다. 연도를 지정해 주세요.")

    total_original_rows = len(df)
    year_col = get_year_col(df)
    if not label_column:
        label_column = get_entity_col(df)

    if not year_col or not label_column:
        raise ValueError("연도 열 또는 국가 식별 열을 찾을 수 없습니다.")

    if x_column not in df.columns or y_column not in df.columns:
        raise ValueError(f"'{x_column}' 또는 '{y_column}' 열이 데이터셋에 존재하지 않습니다.")

    excluded_reasons = []
    total_excluded = 0

    work_df = df[df[year_col].astype(str) == str(reference_period)].copy()
    diff_period = total_original_rows - len(work_df)
    total_excluded += diff_period
    excluded_reasons.append(f"기준시점({reference_period}년) 외 {diff_period}행 제외")

    work_df, agg_exc, agg_reason = filter_aggregates_if_needed(work_df, exclude_aggregates=exclude_aggregates, entity_col=label_column)
    if agg_exc > 0:
        total_excluded += agg_exc
        excluded_reasons.append(agg_reason)

    valid_df = work_df[[label_column, x_column, y_column]].dropna()
    diff_null = len(work_df) - len(valid_df)
    if diff_null > 0:
        total_excluded += diff_null
        excluded_reasons.append(f"결측치 {diff_null}행 제외")

    if len(valid_df) < 3:
        raise ValueError("상관계수를 계산하기 위한 유효 데이터 쌍이 부족합니다.")

    r_val = float(valid_df[x_column].corr(valid_df[y_column]))

    scatter_points = [
        {
            "x": sanitize_value(row[x_column]),
            "y": sanitize_value(row[y_column]),
            "label": ko_country(str(row[label_column]))
        }
        for _, row in valid_df.iterrows()
    ]

    abs_r = abs(r_val) if not math.isnan(r_val) else 0
    if abs_r >= 0.7:
        strength = "매우 강한 상관관계"
    elif abs_r >= 0.4:
        strength = "중간 정도의 상관관계"
    else:
        strength = "약한 상관관계"

    x_ko = ko_sector(x_column)
    y_ko = ko_sector(y_column)

    return sanitize_value({
        "tool": "correlation_scatter",
        "reference_period": f"{reference_period}년",
        "used_rows": len(valid_df),
        "excluded_rows": total_excluded,
        "exclusion_reason": "; ".join(excluded_reasons),
        "used_columns": [year_col, label_column, x_column, y_column],
        "unit": "r (상관계수: -1.0 ~ +1.0)",
        "caution": "★ [중요] 상관관계는 인과관계가 아닙니다. 두 부문 간 상관계수가 높다고 해서 한 부문의 배출이 다른 부문 배출의 직접적인 원인이 됨을 의미하지는 않습니다.",
        "data": {
            "x_column": x_ko,
            "y_column": y_ko,
            "correlation_coefficient_r": r_val,
            "correlation_strength": strength,
            "sample_size": len(valid_df)
        },
        "chart": {
            "type": "scatter",
            "title": f"{reference_period}년 {x_ko} vs {y_ko} 상관관계 산점도 (r = {r_val:.3f})",
            "datasets": [{
                "label": f"국가별 배출량 분포 (r={r_val:.3f}, {strength})",
                "data": scatter_points
            }]
        }
    })

# ==========================================================
# 12. compare_one_vs_all
# ==========================================================
def compare_one_vs_all(df, target_entity, value_column, reference_period, label_column=None, exclude_aggregates=True):
    if not reference_period:
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다. 연도를 지정해 주세요.")
    if not target_entity:
        raise ValueError("비교 대상 엔티티(target_entity)를 지정해 주세요.")

    total_original_rows = len(df)
    year_col = get_year_col(df)
    if not label_column:
        label_column = get_entity_col(df)

    if not year_col or not label_column:
        raise ValueError("연도 열 또는 국가 식별 열을 찾을 수 없습니다.")

    if value_column not in df.columns:
        raise ValueError(f"'{value_column}' 열이 데이터셋에 존재하지 않습니다.")

    excluded_reasons = []
    total_excluded = 0

    work_df = df[df[year_col].astype(str) == str(reference_period)].copy()
    diff_period = total_original_rows - len(work_df)
    total_excluded += diff_period
    excluded_reasons.append(f"기준시점({reference_period}년) 외 {diff_period}행 제외")

    work_df, agg_exc, agg_reason = filter_aggregates_if_needed(work_df, exclude_aggregates=exclude_aggregates, entity_col=label_column)
    if agg_exc > 0:
        total_excluded += agg_exc
        excluded_reasons.append(agg_reason)

    # 한글 입력 대응: '대한민국', '한국' 입력 시 'South Korea' 자동 매칭
    target_clean = str(target_entity).strip().lower()
    if target_clean in ['대한민국', '한국', 'korea', 'south korea', 'rok']:
        target_clean = 'south korea'

    target_match = work_df[work_df[label_column].astype(str).str.lower() == target_clean]
    if target_match.empty:
        # 영문 대소문자 확인
        target_match = work_df[work_df[label_column].astype(str).str.lower().str.contains(target_clean)]

    if target_match.empty:
        raise ValueError(f"'{target_entity}' 국가를 {reference_period}년도 데이터에서 찾을 수 없습니다.")

    target_val = float(target_match[value_column].iloc[0])
    orig_target_name = str(target_match[label_column].iloc[0])
    display_target_name = ko_country(orig_target_name)

    s = work_df[value_column].dropna()
    mean_val = float(s.mean())
    median_val = float(s.median())
    max_val = float(s.max())
    min_val = float(s.min())

    percentile = round(float((s < target_val).mean() * 100), 1)
    sec_ko = ko_sector(value_column)

    chart_labels = [display_target_name, "전 세계 평균 (Mean)", "전 세계 중앙값 (Median)"]
    chart_values = [target_val, mean_val, median_val]

    return sanitize_value({
        "tool": "compare_one_vs_all",
        "reference_period": f"{reference_period}년",
        "used_rows": len(s),
        "excluded_rows": total_excluded,
        "exclusion_reason": "; ".join(excluded_reasons),
        "used_columns": [year_col, label_column, value_column],
        "unit": "tCO2e (톤 CO2 환산량)",
        "caution": f"비교 대상({display_target_name})은 전체 {len(s)}개국 중 상위 {100 - percentile:.1f}%에 해당합니다.",
        "data": {
            "target": display_target_name,
            "target_value": target_val,
            "global_mean": mean_val,
            "global_median": median_val,
            "global_max": max_val,
            "global_min": min_val,
            "percentile_rank": percentile,
            "evaluated_countries_count": len(s)
        },
        "chart": {
            "type": "bar",
            "title": f"{reference_period}년 {display_target_name} vs 전 세계 평균/중앙값 ({sec_ko})",
            "labels": chart_labels,
            "datasets": [{
                "label": f"{sec_ko} 배출량 (tCO2e)",
                "data": [sanitize_value(v) for v in chart_values]
            }]
        }
    })
