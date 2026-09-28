/**
 * Native Oh My Pi Hook: Session Observer & Knowledge Distillation Daemon.
 * Automatically initializes on session start and runs periodic audits
 * to maintain the Single Source of Truth and update documentation.
 */

export default function hook(pi) {
  let turnCount = 0;
  let lastAuditTurn = 0;
  const AUDIT_INTERVAL_TURNS = 5;

  pi.setLabel("BSCU Session Observer");

  // 1. Session Start Event
  pi.on("session_start", async (_event, ctx) => {
    turnCount = 0;
    lastAuditTurn = 0;

    if (ctx.hasUI && ctx.ui.notify) {
      ctx.ui.notify(
        "[Session Observer] Kích hoạt giám sát tự động (chu kỳ: 5 turns / định kỳ)",
        "info"
      );
    }

    // Set managed background periodic timer (every 5 minutes)
    if (ctx.setInterval) {
      ctx.setInterval(async () => {
        try {
          await runAudit(pi, ctx, "Định kỳ Timer (5 phút)");
        } catch (e) {
          // contained error
        }
      }, 5 * 60 * 1000);
    }
  });

  // 2. Turn End Event
  pi.on("turn_end", async (_event, ctx) => {
    turnCount++;

    // Trigger audit every 5 turns
    if (turnCount - lastAuditTurn >= AUDIT_INTERVAL_TURNS) {
      lastAuditTurn = turnCount;
      await runAudit(pi, ctx, `Chu kỳ ${turnCount} turns`);
    }
  });

  async function runAudit(pi, ctx, triggerReason) {
    try {
      const res = await pi.exec("python", ["scripts/audit_session_learnings.py"]);
      if (res.exitCode !== 0) {
        if (ctx.hasUI && ctx.ui.notify) {
          ctx.ui.notify(
            `[Session Observer] Cảnh báo kiểm toán (${triggerReason}): Cần đồng bộ tài liệu docs/`,
            "warning"
          );
        }
      }
    } catch (e) {
      // background execution fail-safe
    }
  }
}
