#!/bin/bash
# ORCA 批量运行脚本 (dpdispatcher Task.command 调用)。
# 遍历工作目录下所有 .inp, 逐个运行 orca, 生成同名 .out。
#
# 注意:
#   - 调度器头 (#BSUB / #SBATCH 等) 由 dpdispatcher 依据 resources 配置自动生成,
#     不应写在本脚本中。本脚本只负责实际的 ORCA 计算。
#   - ORCA 并行 (nprocs>1) 必须用 orca 的绝对路径, 否则 MPI 无法定位子进程。
#   - 环境与路径参照 JLU184 服务器 (sub_orca.sh), 可用环境变量覆盖:
#       ORCA_EXE  orca 可执行文件绝对路径
#       ORCA_ENV  运行前 source 的环境脚本 (设为空则跳过)

set -o pipefail
ulimit -s unlimited

ORCA_EXE="${ORCA_EXE:-/data/home/miwenhui/soft/orca_6_1_0_avx2/orca}"
ORCA_ENV="${ORCA_ENV:-/data/home/miwenhui/soft/orca.sh}"

# 加载 ORCA 运行环境 (若脚本存在)
if [ -n "${ORCA_ENV}" ] && [ -f "${ORCA_ENV}" ]; then
    # shellcheck disable=SC1090
    source "${ORCA_ENV}"
fi
set -u

shopt -s nullglob
inputs=(./*.inp)
if [ "${#inputs[@]}" -eq 0 ]; then
    echo "No ORCA .inp inputs found" >&2
    exit 2
fi

status=0
for inp in "${inputs[@]}"; do
    full_name="$(basename "${inp}")"
    base_name="${full_name%.*}"
    if ! "${ORCA_EXE}" "${inp}" > "${base_name}.out" 2>&1; then
        echo "ORCA failed: ${inp}" >&2
        status=1
        continue
    fi
    if ! grep -qi "ORCA TERMINATED NORMALLY" "${base_name}.out"; then
        echo "ORCA output incomplete: ${base_name}.out" >&2
        status=1
    fi
done
exit "${status}"
