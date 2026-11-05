# film-date-agent

> **「写真にレトロな日付スタンプを入れて」と言えば、フィルム乳剤へのリアルな光学露光が焼き付く。**

AIエージェントおよびCLIから利用するための本格フィルム日付スタンプ（クォーツデート）合成ツール。  
[FilmDateStamp](https://github.com/treeturtlefall-arch/FilmDateStamp)（ComfyUIカスタムノード）の物理光学露光シミュレーションエンジンをそのまま内蔵し、**エージェントと描画エンジンの間の薄い翻訳層（CLI & スキル定義）** を担います。

単なる「文字の貼り付け（透過オーバーレイ）」ではなく、**フィルム乳剤へのLED露光（物理的な光の焼き付け）** をシミュレートします。

---

## 🌟 主な特徴

- 🎞️ **物理光学露光（Optical Burn-in）シミュレーション**  
  中心フィラメント芯の白飛び（ブリーチ）、波長別の分光感光飽和、多重スケールPSFハレーション拡散、LED素子の個体差や圧板浮きの有機的ゆらぎを完全再現。
- 📷 **写真のEXIF撮影日時（DateTimeOriginal）を自動反映**  
  `-d photo` を指定するだけで、写真ファイルのメタデータから当時の撮影日時を自動抽出し、正確な日付・時刻を焼き付けます。
- 🎨 **時代・地域を象徴する12種類のスタイルプリセット**  
  `Japanese Tokyo 90s`（アンバー・80s 7セグ）、`Japanese Snap (Disposable)`（写ルンです風・時分併記オレンジドット）、`American West Coast`（西海岸ロードトリップ）、`American 80s (Red Quartz)`（モーテル赤色LED）、`Cyber Telemetry`（SF映画サイバーグリーン）などワンタッチで世界観を再現。
- 🔤 **自社製TrueTypeを含む厳選8フォント同梱**  
  1980年代諏訪精工舎モジュール実機準拠7セグ（-7°/0°）、写ルンです風カプセルドット、1970年代活字彫刻（Canodate/Datematic）、液晶等幅、SFテレメトリ、平成レトロ丸文字、古文書スクリプト。
- 🎭 **マスク画像（PNG）の同時出力対応**  
  `--save-mask mask.png` により、スタンプの発光領域アルファマスクを出力可能。後続の画像編集ツールで文字部分に粒子を乗せたり、除去・インペイントする用途にも活用できます。
- ⚡ **超軽量 & 高速（PyTorch / GPU不要）**  
  純粋な NumPy + Pillow のみで実装されており、ComfyUI や PyTorch のインストールは一切不要。数十ミリ秒〜1秒程度で軽快に動作します。

### 🗣️ 設定変更は「普通の言葉」でエージェントに伝えるだけ

コマンドやオプションを覚える必要はありません。対応する AI エージェント（Muse / Claude / Gemini 等）に、普段の言葉で頼むだけで設定が伝わります。エージェント側のスキル定義が、言葉をプリセットとオプションに変換します。

| こう伝える | エージェントが実行する内容 |
|---|---|
| 「この写真に日付スタンプを入れて」 | 既定のお気に入り（`Japanese Snap (Disposable)`）で焼き付け |
| 「写ルンですっぽくして」「90年代東京スナップ風で」 | 世界観に合うプリセットへ切り替え |
| 「撮影日時を焼き付けて」「EXIF の日付で」 | 写真の EXIF 撮影日時を自動反映（`--date photo`） |
| 「時間も入れて」「日付だけでいい」 | 時刻（HH:MM）の表示 ON / OFF |
| 「1998年12月24日にして」 | 指定した日付で焼き付け |
| 「この設定をいつものにして」 | 現在の設定をお気に入り（favorite）として保存 |

「いつもの設定」自体も言葉で変えられます（例: 「お気に入りを 90 年代東京風に変えて」）。細かい色・フォント・発光の強さなどのカスタムプリセット作成も、エージェントに相談すれば対話しながら作れます。

---

## 📸 Before / After

既定のお気に入り `Japanese Snap (Disposable)`（写ルンです風・オレンジドット・時分併記）で焼き付けた例です。文字を「貼る」のではなく、フィルム乳剤への光の露光として再現しているため、濡れた路面のような暗い背景の上でも発光とハレーションが自然に馴染みます。

**Before**

![Before](docs/images/before.jpg)

**After**（`'98 12 24 18:30` を焼き付け）

![After](docs/images/after.jpg)

---

## 🤖 AIエージェント向け導入ガイド

AIエージェント（Muse / Claude / Gemini / Antigravity 等）は以下のステップで自律導入・検証してください。

### 1. インストール

最短ルート（推奨）: クローンして一括導入スクリプトを実行する。venv 作成、パッケージ導入、`~/.local/bin` へのコマンド登録、doctor 検証までを自動で行う。

```bash
git clone https://github.com/treeturtlefall-arch/FilmDateStamp-agent.git
cd FilmDateStamp-agent
bash scripts/install_agent.sh
```

手動で行う場合は、先に venv を作ってからその中へ導入すること。システム Python への直接の `pip install` は PEP 668（externally-managed）で弾かれる環境が多い。

```bash
python3 -m venv .venv
.venv/bin/pip install .        # 利用側は非 editable でよい。-e は開発者向け
ln -sf "$PWD/.venv/bin/film-date-agent" ~/.local/bin/film-date-agent
```

### 2. スキル定義の配置
```bash
# Linux / macOS
bash scripts/install_skill.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts\install_skill.ps1
```

### 3. 診断（Doctor チェック）
```bash
film-date-agent doctor --json
```
`"ok": true` であれば準備完了です。

### エージェントの実行ルール（要約）
- **基本呼び出し**:
  ```bash
  film-date-agent apply <対象画像パス> --json
  ```
- **撮影日時を反映**:
  ```bash
  film-date-agent apply <対象画像パス> --date photo --json
  ```
- **写ルンです風に時分付きで**:
  ```bash
  film-date-agent apply <対象画像パス> --preset japanese-snap-disposable --json
  ```
- **結果の報告**: `--json` の出力をパースし、`"ok": true` であれば `"output"` の画像を添付し、焼き付けた日時（`"date_text"`）を一言添えてユーザーに報告します。
- **詳細なトリガーや対応ルール**: [`skill/SKILL.md`](skill/SKILL.md) を参照してください。

---

## 💻 CLI の使い方

### 基本コマンド

```bash
# 1. 既定のお気に入り設定で焼き付け（Japanese Snap (Disposable)）
film-date-agent apply photo.jpg

# 2. 写真のEXIF撮影日時を使って焼き付け
film-date-agent apply photo.jpg --date photo

# 3. 写ルンです風プリセットで時刻（HH:MM）も併記
film-date-agent apply photo.jpg --preset japanese-snap-disposable --show-time

# 4. 指定日時を焼き付け
film-date-agent apply photo.jpg -d "'98 12 24"
film-date-agent apply photo.jpg --at 1998-12-24T18:30 --show-time

# 5. 発光アルファマスクも同時に保存
film-date-agent apply photo.jpg --save-mask mask.png

# 6. フォルダ内の全画像を一括処理（各画像のEXIF日時を反映）
film-date-agent batch input_dir output_dir --date photo --json
```

### プリセットとお気に入りの管理

```bash
# 利用可能なプリセット一覧
film-date-agent presets list

# プリセットの詳細確認
film-date-agent presets show japanese-tokyo-90s

# お気に入りの変更（次回から無指定時に適用される）
film-date-agent presets set-favorite japanese-snap-disposable

# 自分好みのカスタムプリセットを作成して保存
film-date-agent presets create my-vintage --base japanese-tokyo-90s --color "Cyber Green" --show-time
```

### 診断と能力カタログ

```bash
# 依存関係・フォント・エンジン整合性の診断
film-date-agent doctor

# 利用可能な色・フォント・プリセットの一覧カタログ（JSON出力対応）
film-date-agent capabilities --json
```

---

## 📄 ライセンス

MIT License
同梱フォントのライセンスは [`src/film_date_agent/engine/fonts/LICENSE-OFL.txt`](src/film_date_agent/engine/fonts/LICENSE-OFL.txt) を参照してください。
