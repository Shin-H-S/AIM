import { redirect } from "next/navigation";

// 로그인 화면이 첫 페이지(/)로 이동했다. 기존 북마크/링크 호환용 리다이렉트.
export default function LoginPage() {
  redirect("/");
}
