"use client";

import { useState } from "react";
import { downloadArtifact, type ArtifactDownloadResult } from "@/lib/api";

type ArtifactDownloadButtonProps = {
  artifactId: string;
  accessToken: string;
  label?: string;
};

type ButtonState = "idle" | "downloading" | "success" | "error";

export function ArtifactDownloadButton({
  artifactId,
  accessToken,
  label = "다운로드"
}: ArtifactDownloadButtonProps) {
  const [state, setState] = useState<ButtonState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();

  const handleDownload = async () => {
    if (!trimmedToken) {
      setState("error");
      setMessage("다운로드하려면 Bearer token이 필요합니다.");
      return;
    }

    setState("downloading");
    setMessage(null);

    const result = await downloadArtifact({
      artifactId,
      accessToken: trimmedToken
    });

    if (result.state !== "success") {
      setState("error");
      setMessage(getDownloadErrorMessage(result.state));
      return;
    }

    triggerBrowserDownload(result.blob, result.filename);
    setState("success");
    setMessage("다운로드를 시작했습니다.");
  };

  return (
    <div className="flex flex-col items-start gap-2">
      <button
        className="rounded-xl border border-cyan-300 dark:border-cyan-800 bg-cyan-50 dark:bg-cyan-950 px-3 py-2 text-xs font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-100 dark:hover:bg-cyan-900/60 disabled:cursor-not-allowed disabled:opacity-50"
        type="button"
        disabled={!trimmedToken || state === "downloading"}
        onClick={() => {
          void handleDownload();
        }}
      >
        {state === "downloading" ? "다운로드 중" : label}
      </button>
      {message && (
        <p
          className={`text-xs ${
            state === "error" ? "text-rose-700 dark:text-rose-300" : "text-emerald-700 dark:text-emerald-400"
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}

function triggerBrowserDownload(blob: Blob, filename: string) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

function getDownloadErrorMessage(
  state: Exclude<ArtifactDownloadResult["state"], "success">
): string {
  switch (state) {
    case "unauthorized":
      return "인증에 실패했거나 이 artifact에 접근할 권한이 없습니다.";
    case "not-found":
      return "artifact 파일을 찾을 수 없습니다.";
    case "conflict":
      return "현재 storage backend에서는 바로 다운로드할 수 없습니다.";
    case "unavailable":
      return "artifact 다운로드 요청에 실패했습니다.";
  }
}
