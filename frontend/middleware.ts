import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const truthyValues = new Set(["1", "true", "yes", "on"]);

function isDisabled(val: string | undefined) {
  return !!val && truthyValues.has(val.trim().toLowerCase());
}

export function middleware(request: NextRequest) {
  if (!isDisabled(process.env.DISABLE_SIGN_UPS)) {
    return NextResponse.next();
  }

  // Block the UI registration page
  if (request.nextUrl.pathname === "/register") {
    return NextResponse.redirect(new URL("/login", request.nextUrl));
  }

  // Block the BetterAuth sign-up API endpoint
  if (request.nextUrl.pathname === "/api/auth/sign-up/email") {
    return new NextResponse(
      JSON.stringify({ error: "Registrations are currently disabled." }),
      { status: 403, headers: { "Content-Type": "application/json" } }
    );
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/register", "/api/auth/sign-up/email"],
};
