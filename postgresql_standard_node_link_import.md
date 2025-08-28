# PostgreSQL CSV Import Summary (standard_node_link)

This document summarizes the steps used to import the large `node_link_2023.csv` into a local PostgreSQL database table `node_link`, including handling of Korean encoding and header quirks.

## Environment
- OS: macOS
- PostgreSQL: 15 (Postgres.app)
- Shell: zsh
- Working directory: `workspace/standard_node_link`

## Source file
- File: `node_link_2023.csv`
- Size: ~48MB, 542,705 lines
- Encoding: EUC-KR (Korean)
- Headers: Two lines (Korean column names, then English names in parentheses)

Sample first lines (after UTF-8 conversion):
```text path=null start=null
링크아이디,시점노드,시점노드명,종점노드,종점노드명,도로등급,도로명,연장(M),링크권역
(LINK_ID),(F_NODE),(NODE_NAME),(T_NODE),(NODE_NAME),(ROAD_RANK),(ROAD_NAME),(len),(organ)
1000000301,1000008600,종로구청입구교차로,1000008900,SK빌딩,103,종로,150.9259734,서울특별시
```

## Steps

### 1) Inspect file and encoding
```bash path=null start=null
ls -lh node_link_2023.csv
wc -l node_link_2023.csv
head -1 node_link_2023.csv | hexdump -C
iconv -f euc-kr -t utf-8 node_link_2023.csv | head -3
```

### 2) Convert EUC-KR to UTF-8 (robust handling)
`iconv` hit a conversion error on a specific line, so a Python fallback with `errors='ignore'` was used.
```bash path=null start=null
python3 - <<'PY'
with open('node_link_2023.csv', 'r', encoding='euc-kr', errors='ignore') as f:
    data = f.read()
with open('node_link_2023_utf8.csv', 'w', encoding='utf-8') as w:
    w.write(data)
print('Conversion completed')
PY
```

### 3) Remove the second header line
The CSV contains two header lines. We skipped both by creating a data-only file starting from line 3.
```bash path=null start=null
tail -n +3 node_link_2023_utf8.csv > node_link_data_only.csv
```

### 4) Create the target table
```sql path=null start=null
CREATE TABLE IF NOT EXISTS node_link (
    link_id BIGINT PRIMARY KEY,
    f_node BIGINT,
    f_node_name VARCHAR(100),
    t_node BIGINT,
    t_node_name VARCHAR(100),
    road_rank INTEGER,
    road_name VARCHAR(200),
    length_m DECIMAL(15,8),  -- adjusted to handle larger values like 17062.26787
    organ VARCHAR(50)
);
```

Note: Initially `length_m` used DECIMAL(12,8) which overflowed on some rows; it was updated to DECIMAL(15,8).

### 5) Import data efficiently
```bash path=null start=null
psql -c "\\copy node_link FROM 'node_link_data_only.csv' DELIMITER ',' CSV;"
```

Result: `COPY 542703`

### 6) Verify import
```bash path=null start=null
psql -c "SELECT COUNT(*) FROM node_link;"     # 542703
psql -c "SELECT * FROM node_link LIMIT 3;"   # spot-check rows
```

### 7) Create useful indexes
```sql path=null start=null
CREATE INDEX idx_node_link_f_node     ON node_link(f_node);
CREATE INDEX idx_node_link_t_node     ON node_link(t_node);
CREATE INDEX idx_node_link_road_rank  ON node_link(road_rank);
CREATE INDEX idx_node_link_organ      ON node_link(organ);
CREATE INDEX idx_node_link_road_name  ON node_link(road_name);
```

### 8) Example data check
```sql path=null start=null
SELECT organ, COUNT(*) AS record_count, AVG(length_m) AS avg_length
FROM node_link
GROUP BY organ
ORDER BY record_count DESC;
```

## Notes and gotchas
- Encoding: The original file is EUC-KR; convert to UTF-8 before loading to avoid garbled text.
- Double header: The second header line with English labels will break COPY with HEADER; remove or skip it.
- Numeric precision: Ensure `length_m` has sufficient precision/scale for the largest values in the file.
- Performance: Use `COPY` instead of per-row INSERTs and add indexes after the import when possible.

## Cleanup (optional)
Temporary files created during import can be removed:
```bash path=null start=null
rm node_link_2023_utf8.csv node_link_data_only.csv
```

## Repro quick-start (condensed)
```bash path=null start=null
# 1) Convert encoding
python3 - <<'PY'
with open('node_link_2023.csv', 'r', encoding='euc-kr', errors='ignore') as f:
    data = f.read()
with open('node_link_2023_utf8.csv', 'w', encoding='utf-8') as w:
    w.write(data)
PY

# 2) Remove second header line
tail -n +3 node_link_2023_utf8.csv > node_link_data_only.csv

# 3) Create table and import
psql -c "CREATE TABLE IF NOT EXISTS node_link (link_id BIGINT PRIMARY KEY, f_node BIGINT, f_node_name VARCHAR(100), t_node BIGINT, t_node_name VARCHAR(100), road_rank INTEGER, road_name VARCHAR(200), length_m DECIMAL(15,8), organ VARCHAR(50));"
psql -c "\\copy node_link FROM 'node_link_data_only.csv' DELIMITER ',' CSV;"

# 4) Indexes
psql -c "CREATE INDEX IF NOT EXISTS idx_node_link_f_node ON node_link(f_node);"
psql -c "CREATE INDEX IF NOT EXISTS idx_node_link_t_node ON node_link(t_node);"
psql -c "CREATE INDEX IF NOT EXISTS idx_node_link_road_rank ON node_link(road_rank);"
psql -c "CREATE INDEX IF NOT EXISTS idx_node_link_organ ON node_link(organ);"
psql -c "CREATE INDEX IF NOT EXISTS idx_node_link_road_name ON node_link(road_name);"
```

