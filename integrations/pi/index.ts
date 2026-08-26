import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { settlePiTurn } from "./adapter.ts";

export default function zxroSettlement(pi: ExtensionAPI) {
  pi.on("agent_settled", async (_event, ctx) => {
    const finalMessage = [...ctx.sessionManager.getBranch()]
      .reverse()
      .find((entry) => entry.type === "message" && entry.message.role === "assistant");
    try {
      await settlePiTurn(finalMessage?.type === "message" ? finalMessage.message : undefined);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      ctx.ui.notify(`zxro settlement failed: ${message}`, "error");
      console.error(`zxro settlement failed: ${message}`);
      throw error;
    }
  });
}
