# 公式与页面继承通用子规格

这是模板中间契约的扩展，不是Word生成器。没有预置校名、纸张大小、边距、公式编号样式或制表位。未知属性使用 unresolved，不填推测值来通过检查。

## 公式分为四个独立层次

### 数学内容与可编辑性 equation.content

structured data：representation（omml/image/plain_text）、editable_required、display_mode（inline/display）、source_notation（latex/mathml/omml/other）、preserve_math_semantics。

要求可编辑时，当前支持的目标只能声明 OMML 原生Word数学对象；图片、普通字符串或遗留LaTeX均不能当成可编辑公式。这里采用保守的OMML路径，尚未实现或认证OLE等其他可编辑数学对象。转换须保留上下标、分式、根式、矩阵、求和上下限、希腊字母、单位与符号，不改研究公式。变量斜体、矢量粗斜体、函数/单位正体等另以数学角色的font规则表示；不得给整条公式统一斜体。先验证转换器对稿件实际语法的覆盖，失败报告，不静默截图兜底。

### 显示与编号布局 equation.layout

data：formula_alignment；numbered；number_alignment；number_pattern（有编号必须含`{number}`）；separation（tab_stops/borderless_layout_table/inline/none）；leader（none/dots/dashes）；long_formula_break；keep_number_with_formula。

公式与编号是两个相关对象。提取居中/右对齐、编号括号、长公式折行点、行距、上下留白、分页保持，以及公式样式实际制表位。几何位置使用现有`equation.tab_stops`、段落和留白规则；不把旧版心的制表位直接用于新节。Tab布局和无边框布局表是实现选择，不能伪称模板文字；必须记录理由并测试。布局表不属于正文数据表，不套三线表。禁止用连续空格定位，禁止编号单独换行、公式裁切或因较长而改写数学内容。

### 编号计数与更新 equation.numbering

data：scope（chapter/document/custom）、counter_id、start、continuous、unique、reset_on_scope_change、update_mode（static/word_fields/backend_rebuild）。实例依据模板设定起始号和显示规则；自定义范围需另附完整定义。图、表、公式范围一致时，通过`numbering.consistency`连接角色，但各用独立计数器，不共用同一条序列。

Word字段路径可使用经过测试的SEQ/REF等；逐章计数须明确章节值与重启机制，不能只拼显示字符串。字段代码存在不代表缓存已更新；声明word_fields或backend_rebuild之前，要真实测试“在前面插入一条公式→重新编号→引用显示更新”。静态编号若仅满足当前导出，须如实说明不支持编辑后自动更新。

### 内部引用与跳转 equation.navigation

data：target_role_id、anchor_policy=stable_unique_bookmark、display（target_number/source_label）、link_required、target_match_required、update_mode、verification。

每个真实公式实例需唯一稳定标识，不能用易变化的段落序号或当前显示编号充当唯一身份。稿件链接→公式实例→Word书签→编号→引用显示应有映射表；target_role_id只约束对象类别，不能替代实例级映射。书签须遵守Word命名约束、ID唯一、起止完整；复制模板或插入内容后不得重复ID。若链接须显示编号，显示必须由目标编号派生而非沿用旧Markdown标签。

verification可列：structural_target、display_matches_number、click_target、after_edit_update。要求跳转时必须列结构目标和真实点击验收；可更新时必须列编辑后验收。当前验证器检查这些要求是否写入，而不执行点击、不证明Word交互通过。

## 页面设置优先从模板副本继承

`page.source_inheritance` data：strategy（copy_template/rebuild_from_source_settings）、source_id、section_locator_ids、properties、original_immutable、work_on_copy、section_policy、header_footer_policy、page_number_policy、verify_effective_settings。

properties按实际范围选size、orientation、margins、gutter、header_footer_distance、columns、grid。尺寸仍由已有page.width/height/margin等属性分别表达或保留来源；“源文件继承”不是`inherits_rule_id`——后者只指契约内同属性规则继承。

优先路径：源DOCX不变→创建工作副本→定位并填入稿件→保留经过审阅的页面属性。即使不重建页面设置，也必须读取并保存它们，才可比较生成前后是否误改。复制文件不是批准源模板所有内容：教学段落、范文、无关签名页等仍按任务边界处理。

逐节记录纸张、方向、四边距、装订线、栏、网格、页眉页脚距离；另外记录节类型、首页/奇偶页、页眉页脚引用与继承、页码格式及重启。`sectPr`在正文中终止其所属节，不把它所在段落当下一节起点。删段、插页、移除不交付区域时必须将节重新映射到封面/摘要/正文等实际区域，避免最后一个段落的sectPr被意外删除导致前面页面格式改变。

section_policy/header_footer_policy/page_number_policy分开选preserve_reviewed或remap_to_content。前者表示已经审阅后保留，不是盲目照搬；后者要求明确源区域→成稿区域映射、必要差异和证据。复制原模板不保证页眉位置正确、页码不重启、目录准确；填充后仍须对照节设置、检查页眉页脚作用范围并渲染所有成稿页面。

## 验收分层

1. 内容：公式数量、语义结构、稿件与目标对应，禁止新增或改写研究公式。
2. 结构：OMML存在且内容有效；书签和字段/链接目标存在，编号及引用无悬空；源、目标节映射可追溯。
3. 显示：公式、编号、留白、长公式与分页正确；页面设置与保留来源或批准差异一致。
4. 交互：在Word中可编辑公式、点击到正确对象；另行验证插入/删除后的更新。仅PDF不能验证Word编辑/点击能力。

本次仅新增规格与机械检查测试。未实现公式转换、编号字段生成、Word交互验收或模板副本填充后端；契约可读不等于成稿可用。
