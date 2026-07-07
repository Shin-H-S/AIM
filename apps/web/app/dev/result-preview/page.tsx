import { notFound } from "next/navigation";
import { ResultPreviewGallery } from "./ResultPreviewGallery";

// 개발 검수용 갤러리 — 프로덕션 빌드에서는 404를 반환한다.
export default function ResultPreviewPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return <ResultPreviewGallery />;
}
