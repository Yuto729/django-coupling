# django-coupling

[English](README.md) | **日本語**

Django / Python プロジェクトの**結合度を可視化する**ツール。Rust の
[`cargo-coupling`](https://github.com/nwiizo/cargo-coupling) を Python に移植したもので、
Vlad Khononov の *Balancing Coupling in Software Design* がベースです。

> **これは Django プロジェクトに対して実行する静的解析 CLI であって、Django アプリではありません。**
> `INSTALLED_APPS` に追加するものではありません。

前提となる考え方：**結合そのものは悪ではなく、アンバランスな結合が悪い。** 強い結合でも、
対象が近い・変わらないなら問題ない。強い結合が「遠い」または「よく変わる」ときに痛む。
このツールは、その判断をベテランの頭の中ではなく**測定可能なシグナルとして外在化**する
（理解負債に対する「fitness function」）。

## 3つの次元

| 次元 | 測るもの | 取得元 |
|---|---|---|
| **Strength（強度）** | あるモジュールが相手にどれだけ深く踏み込んでいるか | `ast` による静的な使われ方 |
| **Distance（距離）** | 構造的な距離 + Django レイヤーの方向 | モジュールパス |
| **Volatility（変動性）** | 依存先がどれだけ頻繁に変わるか | git 履歴 |

```
balance = (1 - |strength - (1 - distance)|) * (1 - volatility * strength)
```
0.0〜1.0、高いほど健全。集約して S〜F のグレードを出す。

### Strength（強度）のレベル
`contract`（0.25、型注釈・基底クラスのみ）< `model`（0.50、共有シンボル参照）<
`functional`（0.75、関数・メソッド呼び出し）< `intrusive`（1.00、`_private` / `._meta` 等の内部に触る）。

1エッジ内に複数の使われ方があれば**最も強いものが勝つ**（1箇所でも内部に触れば intrusive 扱い）。

### Distance（距離）と Django レイヤー
レイヤー順位は `views > serializers > services > models`。上位層が下位層を import するのは
期待される方向（`views → services → models`）。逆流（`models → views`）は **layer violation（critical）**
として検出。同ランクのレイヤー同士は same-layer 扱い（どちら向きでも違反にしない）。

順位はプロジェクト側の判断なので `.coupling.toml` で上書きできる（解析パスから上方向に探索）：

```toml
[layers]
# name = rank（小さいほど上位層）。同ランク => same-layer。
views = 0
serializers = 2   # services と同ランクにすると services <-> serializers は違反にならない
services = 2
models = 3

[analysis]
# 組み込みの除外（__pycache__, migrations, node_modules, venv, .venv, tests/test）に追加するディレクトリ
exclude_dirs = ["seeds_csv", "seeds_json", "generated"]
include_tests = false   # true でテストも解析対象に
```

> 実例：smbkikan-back で `serializers` と `services` を同ランクにすると critical 違反が
> 74 → 19 に減る（残り19は models→上位層などの真の逆流）。

### Volatility（変動性）
直近の期間（既定6ヶ月）にその依存先ファイルを触ったコミット数：
0〜2 → low (0.0)、3〜10 → medium (0.5)、11以上 → high (1.0)。

git は AI コーディング時代にノイズの多いセンサーになる（1コミットが無関係な多数の
ファイルを触る）。そこで複数の対策を組み合わせて硬化している：

- `--no-merges`（マージは実編集ではない）
- `--max-commit-files`（既定30）を超えるコミットは**除外** —— 1つの巨大コミットが
  N個のファイルを一斉に汚染するのを防ぐ
- リポジトリ自身のコミットサイズ分布から**信頼度を自己申告**（`high`/`medium`/`low`）：

  ```
  volatility confidence: high  (median 2 files per commit, 90th percentile 7, 3 of 921 bulk commits (over 30 files) excluded)
  ```

## God クラス検出（クラス粒度）

モジュール単位の結合では「1ファイル内の巨大クラス」が見えない。そこで別パスで
`ast.ClassDef` 粒度の **God クラス候補**を検出する。シグナルは**サイズではなく凝集度**
（サイズは「大きいが凝集」と「何でもやる」を区別できない）：

- **LCOM4** —— メソッドをノードとし、共有する `self.*` メンバ（共有フィールド、または
  互いの呼び出し）で連結したグラフの**連結成分数**。サイズ非依存で、凝集クラスは
  どんな大きさでも1成分、God クラスは2成分以上に分裂する（実質、複数クラスが1つの名前を被っている）。
- 候補化のゲート（recall より precision —— 誤検出は信頼を壊す）：
  - インスタンスフィールドが1つ以上（共有状態が無いと LCOM は無意味。Django Admin /
    FilterSet のフックや純粋関数の寄せ集めを除外）
  - 全メソッド孤立は除外（状態を持たない寄せ集め＝別の smell）
  - テストは除外（テスト→内部の結合は当然）
- `distinct imports used`（クラスが触る import の種類数）を重大度の補助シグナルに。

出力は**断定ではなくレビュー候補**。Facade・DTO・リッチな Django モデルは正当でも高く出る。
**意図的に git 非依存**（co-change は AI 時代の巨大コミットで汚染されすぎて信用できない）。

> smbkikan-back ではゲートにより 314（生）→ 34（実用的な候補）に削減。

## Module summary（ファイル単位の集計）

エッジ単位のデータに加えて、エッジを依存元ファイルで集計する。「このファイルは多方面に
遠く依存している」というシグナルを、消費側がエッジを集計しなくても直接読めるようにするため：

```
Modules by outgoing coupling (efferent, top N):
  efferent edges=31  afferent edges=1  distinct target packages=11  mean distance=0.50  God candidates=0   api.views.shop
```

- **efferent edges** —— 外向き依存数（このファイルが使うモジュール数）
- **afferent edges** —— 内向き被依存数（このファイルに依存するモジュール数）
- **distinct target packages** —— 行き先のパッケージの種類数
- **mean distance** —— 外向きエッジの平均距離
- **God candidates** —— このファイル内の God クラス候補数

外向き依存が多い × 行き先パッケージが多い × God 候補が複数、が揃ったファイルは
**分割候補**（各クラスを依存先の近くへ移す）。注意：re-export の `__init__.py` 集約ファイルは
afferent/efferent が高くて当然で、smell ではない。

## インストール（Nix）

Nix flake として配布（`git` を内部にラップしてあるので volatility がそのまま動く）。

```bash
# ローカルクローンから、インストールせず実行
nix run . -- path/to/project

# プロファイルにインストール
nix profile install .

# GitHub から直接実行
nix run github:Yuto729/django-coupling -- path/to/project

# 開発シェル（pytest + git）
nix develop
```

Nix を使わない場合：依存ゼロの stdlib パッケージなので、クローンから
`pipx install .` / `uvx --from . django-coupling` でも動く。

## 使い方

```bash
django-coupling path/to/package
django-coupling path/to/package --json | jq '.edges[:10]'
django-coupling path/to/package --top 30 --since "3 months ago"
```

ランタイム依存ゼロ（stdlib `ast` + `git`）。

### 差分モード（変更ファイルの悪化を見る）

絶対値は「このコードベースはどれだけ結合しているか」を答える。`--diff` はより
行動につながる **「自分の変更がどれだけ悪化させたか」** を答える。各変更ファイルの
*before*（`git show <ref>:file`）と *after*（作業ツリー）を比較し、**変更ファイルだけ**を
パースする（全体のベース集計は回さない）。

```bash
django-coupling path/to/package --diff           # 作業ツリー vs HEAD
django-coupling path/to/package --diff main       # ブランチ/コミットと比較
django-coupling path/to/package --diff --json     # 機械可読
```

変更ファイルに限定して報告する：**新規 issue**（レイヤー違反・cascading）、
**balance のリグレッション**（エッジの balance 低下）、**新規/悪化した God 候補**、
および変更スコープの balance before → after。**新規 critical が入ると exit 1** —— 既存の
バックログを直さなくても *新規* 違反だけをブロックする CI ratchet として使える。

スコープ：変更ファイルから**出ていくエッジ**のみ。変更していない importer への二次波及
（変更ファイルの volatility 上昇、あるいはレイヤーをまたぐ**移動**）は意図的に対象外。

### AI エージェント向け

AI コーディングエージェント用の中立なリファレンス Skill（いつ使うか・ヘルプコマンド・
出力の解釈方法）を
[`.claude/skills/django-coupling/SKILL.md`](.claude/skills/django-coupling/SKILL.md)
に同梱している。`git clone` して自分のプロジェクトの `.claude/skills/` にコピーすると
Claude Code で使える：

```bash
git clone https://github.com/Yuto729/django-coupling /tmp/django-coupling
mkdir -p .claude/skills
cp -r /tmp/django-coupling/.claude/skills/django-coupling .claude/skills/
rm -rf /tmp/django-coupling   # 後片付け（任意）
```

## v0 のスコープと既知の限界

これは MVP（v0）。意図的に**やっていない**こと：

- `--web` 可視化、`--baseline` 差分ゲート、`--impact` / `--trace`
- Django の ForeignKey / signal による結合（import グラフのみ）
- God クラスの閾値（`--god-min-methods`、フィールド/fan-out ゲート）はヒューリスティック。
  フレームワーク由来のクラス（ViewSet、Admin）は候補に残りうる

`.coupling.toml` は現状 `[layers]` と `[analysis]` のみ対応。その他の閾値
（`max_dependencies` 等）はハードコード。

知っておくべきヒューリスティックの限界：

- インスタンス経由の強度は過小評価される —— `Budget._x` は intrusive と検出するが、
  `b = Budget(); b._x` は検出できない（データフロー解析なし）。
- 既定の順位では `services → serializers` を違反とする。これが「間違い」かは
  アーキテクチャ次第 —— `.coupling.toml` の `[layers]` で上書きを。

結果は断定ではなく指針 —— 人間によるレビューの出発点。

## 開発

```bash
python -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest -q
# または Nix で:
nix develop -c pytest -q
```

## クレジット

- [`cargo-coupling`](https://github.com/nwiizo/cargo-coupling)（[@nwiizo](https://github.com/nwiizo)）の移植。
  Python/Django 向けに再実装したもので、3次元モデル（Strength × Distance × Volatility）と
  Balance Score の式はこれに準拠している。著者の解説記事：
  [導入](https://syu-m-5151.hatenablog.com/entry/2025/12/20/195329) /
  [可視化](https://syu-m-5151.hatenablog.com/entry/2025/12/21/152559)。
- Vlad Khononov *Balancing Coupling in Software Design*（Addison-Wesley）—— Integration
  Strength / Distance / Volatility のフレームワーク。
- 「Django」は Django Software Foundation の登録商標。本ツールは非公式の
  サードパーティ製で、DSF とは無関係・非承認。

## ライセンス

[MIT](LICENSE) © Yuto Mitomi
