# 修复 React #310 崩溃 — 根因与代码质量复盘

## 现象
电商套图前端 UI 重构后，打开「属性设置弹窗」时控制台抛出：
```
Uncaught Error: Minified React error #310
  at useMemo (...index-DeyipCx1.js)
  at Yvt (...index-DeyipCx1.js:754)
```
整个组件树直接崩溃，弹窗无法使用。

## 根因（Rules of Hooks 违规）
`TypeSettingsModal.tsx` 中，`groupedPersonal` 的 `useMemo` 被放在了条件早返回之后：

```tsx
// ❌ 错误写法
const [personal, setPersonal] = useState(...)
...
if (!type) return null          // 早返回在 hook 之前

const groupedPersonal = useMemo(() => {
  // 遍历 type.personal ...
}, [type.personal])
```

- 弹窗关闭（`type === null`）：early return 直接退出，**该 `useMemo` 不执行** → 本帧只跑 25 个 hook
- 弹窗打开（`type` 有值）：不 return，**执行到 `useMemo`** → 本帧跑 26 个 hook
- **hook 数量随渲染变化**，违反 React 的 Rules of Hooks，React 19 在渲染期直接中断（生产 minified 构建即表现为 #310）

## 修复
1. **把 `useMemo` 移到早返回之前**，依赖数组从 `[type.personal]` 改为 `[type]`，函数体内加 `if (!type) return []` 守卫 —— hook 数量恒定，不再随开关变化。

```tsx
// ✅ 正确写法
const groupedPersonal = useMemo(() => {
  if (!type) return []
  // 遍历 type.personal ...
}, [type])

if (!type) return null
```

2. **顺带消除 `PlannerDrawer.tsx` 的「组件定义在组件内部」反模式**：`TypeCard` 原本定义在 `PlannerDrawer` 函数体内，每次父组件渲染都会生成新的函数身份，导致所有类型卡片反复卸载/重挂载（丢焦点、掉性能）。已抽成模块级组件，通过 `isChecked` / `onToggle` props 传值。

## 验证
- `tsc --noEmit` 零类型错误
- `vite build` 成功（4289 模块，零编译错误）

## 给团队的三条硬规范（代码质量把控）
1. **Hooks 必须在组件顶层无条件调用**。任何 `if (...) return` 都要放在所有 hook 声明之后；不能在条件分支里调用 `useState` / `useMemo` / `useEffect` 等。
2. **不要把组件定义在另一个组件内部**。需要复用的子组件一律抽到模块级，交互状态用 props 向下传。
3. **`useMemo` / `useEffect` / `useCallback` 必须显式写依赖数组**，不要依赖「省略第二参数=每次重算」这种隐式行为（React 19 下省略依赖数组本身就是错误）。

> 修复后请 **Ctrl+F5 硬刷新** 浏览器，重新打开属性设置弹窗 / AI 智能策划台验证。
