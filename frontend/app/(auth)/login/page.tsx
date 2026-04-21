"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";

const loginSchema = z.object({
  email: z.string().email("Please enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type LoginFormData = z.infer<typeof loginSchema>;

const truthyParamValues = new Set(["1", "true", "yes", "on"]);

const signUpsDisabledVal = process.env.NEXT_PUBLIC_DISABLE_SIGN_UPS?.trim().toLowerCase();
const signUpsDisabled = ["1", "true", "yes", "on"].includes(signUpsDisabledVal ?? "");

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const demoModeRequested = useMemo(() => {
    const raw = searchParams.get("demo");
    if (!raw) return false;
    return truthyParamValues.has(raw.trim().toLowerCase());
  }, [searchParams]);

  const emailFromQuery = searchParams.get("email")?.trim() || "";
  const demoEmail = process.env.NEXT_PUBLIC_DEMO_EMAIL?.trim() || "";
  const demoPassword = process.env.NEXT_PUBLIC_DEMO_PASSWORD || "";

  const prefillEmail = demoModeRequested
    ? (demoEmail || emailFromQuery)
    : emailFromQuery;
  const prefillPassword = demoModeRequested ? demoPassword : "";

  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: prefillEmail,
      password: prefillPassword,
    },
  });

  useEffect(() => {
    if (prefillEmail) {
      setValue("email", prefillEmail, { shouldDirty: false });
    }
    if (prefillPassword) {
      setValue("password", prefillPassword, { shouldDirty: false });
    }
  }, [prefillEmail, prefillPassword, setValue]);

  // If the user landed here because an OAuth authorize request requires
  // authentication, better-auth's oauth-provider passes the original
  // authorize query (plus `exp` and `sig`) along. After successful sign-in
  // we resume the OAuth flow by re-hitting /api/auth/oauth2/authorize with
  // those same params. Otherwise we fall back to the dashboard.
  const oauthResumeURL = useMemo(() => {
    const hasOauthParams =
      searchParams.has("client_id") &&
      searchParams.has("response_type") &&
      searchParams.has("redirect_uri");
    if (!hasOauthParams) return null;
    return `/api/auth/oauth2/authorize?${searchParams.toString()}`;
  }, [searchParams]);

  const onSubmit = async (data: LoginFormData) => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await signIn.email({
        email: data.email,
        password: data.password,
      });

      if (result.error) {
        setError(result.error.message || "Failed to sign in");
        return;
      }

      if (oauthResumeURL) {
        // Full navigation so the browser follows the authorize redirect chain
        // (consent page → client redirect_uri with code).
        window.location.href = oauthResumeURL;
        return;
      }

      router.push("/");
      router.refresh();
    } catch {
      setError("An unexpected error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Login to your account</CardTitle>
        <CardDescription>
          Enter your email below to login to your account
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <FieldGroup>
            {error && (
              <div className="bg-destructive/10 text-destructive p-3 text-sm">
                {error}
              </div>
            )}
            {demoModeRequested && demoEmail && demoPassword && (
              <div className="bg-muted border border-border p-3 text-sm space-y-1">
                <p className="font-medium text-foreground">Demo account credentials</p>
                <p className="text-muted-foreground">
                  Email: <span className="text-foreground font-mono">{demoEmail}</span>
                </p>
                <p className="text-muted-foreground">
                  Password: <span className="text-foreground font-mono">{demoPassword}</span>
                </p>
              </div>
            )}
            {demoModeRequested && !demoPassword && (
              <div className="bg-muted p-3 text-sm">
                Demo mode link detected, but demo credentials are not configured
                on this deployment.
              </div>
            )}
            <Field>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                type="email"
                placeholder="m@example.com"
                {...register("email")}
                disabled={isLoading}
              />
              {errors.email && (
                <FieldError>{errors.email.message}</FieldError>
              )}
            </Field>
            <Field>
              <div className="flex items-center">
                <FieldLabel htmlFor="password">Password</FieldLabel>
              </div>
              <Input
                id="password"
                type="password"
                {...register("password")}
                disabled={isLoading}
              />
              {errors.password && (
                <FieldError>{errors.password.message}</FieldError>
              )}
            </Field>
            <Field>
              <Button type="submit" disabled={isLoading} className="w-full">
                {isLoading ? "Signing in..." : "Login"}
              </Button>
              {!signUpsDisabled && (
                <FieldDescription className="text-center">
                  Don&apos;t have an account?{" "}
                  <Link href="/register" className="underline underline-offset-4">
                    Sign up
                  </Link>
                </FieldDescription>
              )}
            </Field>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}

function LoginPageFallback() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Login to your account</CardTitle>
        <CardDescription>Loading login form...</CardDescription>
      </CardHeader>
      <CardContent />
    </Card>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginPageFallback />}>
      <LoginPageContent />
    </Suspense>
  );
}
