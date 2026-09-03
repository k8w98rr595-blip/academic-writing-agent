export function EnvironmentBanner({ enabled }: { enabled: boolean }) {
  if (!enabled) return null;
  return <aside aria-label="环境提示" style={{
    width: "100%", boxSizing: "border-box", padding: "8px 12px",
    background: "#fff3cd", color: "#493700", border: "1px solid #e4cb7b",
    fontSize: 12, textAlign: "center",
  }}>本地隔离测试 · Mock · 模拟套餐，不会扣费 · 仅限合成文稿</aside>;
}
