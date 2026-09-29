/**
 * Native Oh My Pi Hook: Session Observer & Knowledge Distillation Daemon.
 * Automatically initializes on session start and runs periodic audits
 * to maintain the Single Source of Truth and update documentation.
 */

export default function hook(pi) {
  pi.setLabel("BSCU Session Observer");

  // Chạy kiểm toán docs ngầm sau mỗi lần AI hoàn thành câu trả lời (turn_end)
  // Hoạt động hoàn toàn trong im lặng (Silent Mode), không popup thông báo/cảnh báo
  pi.on("turn_end", async (_event, ctx) => {
    try {
      await pi.exec("python", ["scripts/audit_session_learnings.py"]);
    } catch (e) {
      // fail-safe: tuyệt đối không ngắt hoặc ảnh hưởng luồng làm việc chính
    }
  });
}
