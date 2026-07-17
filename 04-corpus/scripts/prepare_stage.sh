#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

usage() {
  echo "使い方: ${0} smoke|accuracy|load 1|2|3 [copy|symlink]" >&2
}

stage="${1:-}"
plan="${2:-}"
method="${3:-copy}"

if [[ "${stage}" != "smoke" && "${stage}" != "accuracy" && "${stage}" != "load" ]]; then
  usage
  exit 1
fi
if [[ "${plan}" != "1" && "${plan}" != "2" && "${plan}" != "3" ]]; then
  usage
  exit 1
fi
if [[ "${method}" != "copy" && "${method}" != "symlink" ]]; then
  usage
  exit 1
fi

REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
documents_dir="${REPO_ROOT}/deploy/plan${plan}/documents"
ensure_dir "${documents_dir}"

direct_file="$(find "${documents_dir}" -maxdepth 1 -type f ! -name '.gitkeep' -print -quit)"
if [[ -n "${direct_file}" ]]; then
  echo "documents/ 直下のファイルを検出したため中止します: ${direct_file}" >&2
  echo "laws / whitepaper / ipa / livedoor / wikipedia のいずれかへ移動してください。" >&2
  exit 1
fi
declare -a groups=("laws" "whitepaper")
declare -a sources=("${PROCESSED_DIR}/laws" "${RAW_DIR}/whitepaper")

if [[ "${stage}" == "accuracy" || "${stage}" == "load" ]]; then
  groups+=("ipa" "livedoor")
  sources+=("${RAW_DIR}/ipa" "${RAW_DIR}/livedoor/text")
fi
if [[ "${stage}" == "load" ]]; then
  groups+=("wikipedia")
  sources+=("${PROCESSED_DIR}/wikipedia")
fi

find_corpus_files() {
  local source_dir="${1}"
  shift
  find "${source_dir}" -type f \
    ! -name 'SOURCE.md' \
    ! -name 'LICENSE.txt' \
    ! -name 'CHANGES.txt' \
    ! -name 'README.txt' \
    "${@}"
}

for index in "${!groups[@]}"; do
  source_dir="${sources[${index}]}"
  if [[ ! -d "${source_dir}" ]] || [[ "$(find_corpus_files "${source_dir}" -print -quit)" == "" ]]; then
    echo "必要なコーパスがありません: group=${groups[${index}]} source=${source_dir}" >&2
    echo "先に scripts/corpus/README.md の取得・前処理手順を完了してください。" >&2
    exit 1
  fi
done

copy_tree() {
  local source_dir="${1}"
  local target_dir="${2}"
  local relative
  local source_file
  local target_file
  while IFS= read -r -d '' source_file; do
    relative="${source_file#"${source_dir}/"}"
    target_file="${target_dir}/${relative}"
    ensure_dir "$(dirname "${target_file}")"
    cp -a -v "${source_file}" "${target_file}"
  done < <(find_corpus_files "${source_dir}" -print0)
}

link_tree() {
  local source_dir="${1}"
  local target_dir="${2}"
  local relative
  local source_file
  local target_file
  while IFS= read -r -d '' source_file; do
    relative="${source_file#"${source_dir}/"}"
    target_file="${target_dir}/${relative}"
    ensure_dir "$(dirname "${target_file}")"
    if [[ -L "${target_file}" ]]; then
      if [[ "$(readlink "${target_file}")" == "${source_file}" ]]; then
        echo "リンク済みのためスキップ: ${target_file}"
        continue
      fi
      echo "異なるシンボリックリンクが存在します: ${target_file}" >&2
      exit 1
    fi
    if [[ -e "${target_file}" ]]; then
      echo "通常ファイルと競合するため中止します: ${target_file}" >&2
      exit 1
    fi
    ln -s -v "${source_file}" "${target_file}"
  done < <(find_corpus_files "${source_dir}" -print0)
}

echo "段階 ${stage} / 案 ${plan} / 配置方式 ${method}"
echo "既存の documents/ は削除せず、必要なコーパスを累積配置します。"
if [[ "${method}" == "symlink" ]]; then
  echo "注意: 絶対シンボリックリンクを作成します。Docker ingest では ${CORPUS_DIR} を同じ絶対パスへ read-only 追加マウントしない限りリンク先を参照できません。" >&2
  echo "標準 compose のまま実行する場合は copy を使用してください。" >&2
fi

for index in "${!groups[@]}"; do
  group="${groups[${index}]}"
  source_dir="${sources[${index}]}"
  target_dir="${documents_dir}/${group}"
  ensure_dir "${target_dir}"
  if [[ "${method}" == "copy" ]]; then
    copy_tree "${source_dir}" "${target_dir}"
  else
    link_tree "${source_dir}" "${target_dir}"
  fi
  count="$(find "${target_dir}" \( -type f -o -type l \) -print | wc -l)"
  echo "配置結果: group=${group} files=${count} destination=${target_dir}"
done

total="$(find "${documents_dir}" -mindepth 2 \( -type f -o -type l \) -print | wc -l)"
echo "累積配置完了: ${documents_dir} (${total} files)"
echo "次に対象案の ingest を実行してください。既存コレクション/インデックスは削除され、documents/ 全量から再構築されます。"
