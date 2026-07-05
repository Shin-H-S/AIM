"use client";

import { useEffect, useState } from "react";
import { downloadArtifact, type ArtifactDownloadResult } from "@/lib/api";

type ArtifactImagePreviewProps = {
  artifactId: string;
  accessToken: string;
  alt: string;
};

type PreviewState = "idle" | "loading" | "loaded" | "error";

export function ArtifactImagePreview({
  artifactId,
  accessToken,
  alt
}: ArtifactImagePreviewProps) {
  const [state, setState] = useState<PreviewState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();

  useEffect(() => {
    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [objectUrl]);

  const clearPreview = () => {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
    }
    setObjectUrl(null);
    setState("idle");
    setMessage(null);
  };

  const loadPreview = async () => {
    if (!trimmedToken) {
      setState("error");
      setMessage("미리보기를 불러오려면 Bearer token이 필요합니다.");
      return;
    }

    setState("loading");
    setMessage(null);

    const result = await downloadArtifact({
      artifactId,
      accessToken: trimmedToken
    });

    if (result.state !== "success") {
      setState("error");
      setMessage(getPreviewErrorMessage(result.state));
      return;
    }

    if (result.blob.type && !result.blob.type.startsWith("image/")) {
      setState("error");
      setMessage("이 artifact는 이미지 미리보기를 지원하지 않습니다.");
      return;
    }

    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
    }

    setObjectUrl(URL.createObjectURL(result.blob));
    setState("loaded");
    setMessage(null);
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          className="rounded-xl border border-cyan-300 bg-cyan-50 px-3 py-2 text-xs font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
          type="button"
          disabled={!trimmedToken || state === "loading"}
          onClick={() => {
            void loadPreview();
          }}
        >
          {state === "loading" ? "미리보기 로딩 중" : "실패 스크린샷 미리보기"}
        </button>
        {objectUrl && (
          <button
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 transition hover:bg-slate-50"
            type="button"
            onClick={clearPreview}
          >
            미리보기 닫기
          </button>
        )}
      </div>
      {message && (
        <p className="mt-3 text-xs text-rose-700">
          {message}
        </p>
      )}
      {objectUrl && (
        <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-black/30">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="max-h-[560px] w-full object-contain" src={objectUrl} alt={alt} />
        </div>
      )}
    </div>
  );
}

function getPreviewErrorMessage(
  state: Exclude<ArtifactDownloadResult["state"], "success">
): string {
  switch (state) {
    case "unauthorized":
      return "인증에 실패했거나 이 screenshot artifact에 접근할 권한이 없습니다.";
    case "not-found":
      return "screenshot artifact 파일을 찾을 수 없습니다.";
    case "conflict":
      return "현재 storage backend에서는 screenshot을 바로 미리볼 수 없습니다.";
    case "unavailable":
      return "screenshot 미리보기 요청에 실패했습니다.";
  }
}
