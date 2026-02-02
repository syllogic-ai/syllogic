"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  RiKeyLine,
  RiAddLine,
  RiDeleteBinLine,
  RiFileCopyLine,
  RiCheckLine,
  RiAlertLine,
} from "@remixicon/react";
import { toast } from "sonner";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  createApiKey,
  deleteApiKey,
} from "@/lib/actions/api-keys";
import type { ApiKey } from "@/lib/db/schema";

interface ApiKeysManagerProps {
  initialKeys: Array<{
    id: string;
    name: string;
    keyPrefix: string;
    lastUsedAt: Date | null;
    expiresAt: Date | null;
    createdAt: Date | null;
  }>;
}

type ExpirationOption = "never" | "30days" | "90days" | "1year";

function getExpirationDate(option: ExpirationOption): Date | null {
  if (option === "never") return null;
  const now = new Date();
  switch (option) {
    case "30days":
      return new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    case "90days":
      return new Date(now.getTime() + 90 * 24 * 60 * 60 * 1000);
    case "1year":
      return new Date(now.getTime() + 365 * 24 * 60 * 60 * 1000);
    default:
      return null;
  }
}

function formatDate(date: Date | null): string {
  if (!date) return "Never";
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(date));
}

function formatRelativeTime(date: Date | null): string {
  if (!date) return "Never";
  const now = new Date();
  const d = new Date(date);
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
  return `${Math.floor(diffDays / 365)} years ago`;
}

function isExpired(date: Date | null): boolean {
  if (!date) return false;
  return new Date(date) < new Date();
}

export function ApiKeysManager({ initialKeys }: ApiKeysManagerProps) {
  const router = useRouter();
  const [keys, setKeys] = useState(initialKeys);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [showKeyDialogOpen, setShowKeyDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingKey, setDeletingKey] = useState<typeof keys[0] | null>(null);

  // Form state
  const [keyName, setKeyName] = useState("");
  const [expiration, setExpiration] = useState<ExpirationOption>("never");
  const [isCreating, setIsCreating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Created key state (shown once)
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCreateKey = async () => {
    if (!keyName.trim()) {
      toast.error("Please enter a name for the API key");
      return;
    }

    setIsCreating(true);
    try {
      const result = await createApiKey({
        name: keyName.trim(),
        expiresAt: getExpirationDate(expiration),
      });

      if (result.success && result.apiKey && result.keyData) {
        setKeys([
          {
            id: result.keyData.id,
            name: result.keyData.name,
            keyPrefix: result.keyData.keyPrefix,
            lastUsedAt: null,
            expiresAt: result.keyData.expiresAt,
            createdAt: result.keyData.createdAt,
          },
          ...keys,
        ]);
        setCreatedKey(result.apiKey);
        setCreateDialogOpen(false);
        setShowKeyDialogOpen(true);
        setKeyName("");
        setExpiration("never");
        router.refresh();
      } else {
        toast.error(result.error || "Failed to create API key");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteKey = async () => {
    if (!deletingKey) return;

    setIsDeleting(true);
    try {
      const result = await deleteApiKey(deletingKey.id);
      if (result.success) {
        setKeys(keys.filter((k) => k.id !== deletingKey.id));
        toast.success("API key deleted");
        router.refresh();
      } else {
        toast.error(result.error || "Failed to delete API key");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsDeleting(false);
      setDeleteDialogOpen(false);
      setDeletingKey(null);
    }
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("Copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy to clipboard");
    }
  };

  const configSnippet = createdKey
    ? JSON.stringify(
        {
          mcpServers: {
            "personal-finance": {
              command: "python",
              args: ["-m", "app.mcp.server"],
              env: {
                PERSONAL_FINANCE_API_KEY: createdKey,
              },
            },
          },
        },
        null,
        2
      )
    : "";

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>API Keys</CardTitle>
          <CardDescription>
            Manage API keys for accessing your financial data through the MCP
            server. Use these keys to connect Claude Desktop or other MCP
            clients.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {/* Key list */}
            {keys.length === 0 ? (
              <div className="flex h-24 items-center justify-center rounded border border-dashed">
                <p className="text-sm text-muted-foreground">
                  No API keys yet. Create one to get started.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {keys.map((key) => (
                  <div
                    key={key.id}
                    className="flex items-center justify-between rounded border p-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded bg-muted">
                        <RiKeyLine className="h-4 w-4 text-muted-foreground" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium">{key.name}</p>
                          {isExpired(key.expiresAt) && (
                            <span className="text-xs text-destructive">
                              Expired
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <code className="rounded bg-muted px-1">
                            {key.keyPrefix}...
                          </code>
                          <span>·</span>
                          <span>
                            {key.lastUsedAt
                              ? `Last used ${formatRelativeTime(key.lastUsedAt)}`
                              : "Never used"}
                          </span>
                          <span>·</span>
                          <span>
                            {key.expiresAt
                              ? `Expires ${formatDate(key.expiresAt)}`
                              : "No expiration"}
                          </span>
                        </div>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => {
                        setDeletingKey(key);
                        setDeleteDialogOpen(true);
                      }}
                    >
                      <RiDeleteBinLine className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            {/* Create button */}
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => setCreateDialogOpen(true)}
            >
              <RiAddLine className="mr-2 h-4 w-4" />
              Create API Key
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Create API Key Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create API Key</DialogTitle>
            <DialogDescription>
              Create a new API key to access your financial data through the MCP
              server.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="key-name">Name</Label>
              <Input
                id="key-name"
                placeholder="My API Key"
                value={keyName}
                onChange={(e) => setKeyName(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                A descriptive name to identify this key.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="expiration">Expiration</Label>
              <Select
                value={expiration}
                onValueChange={(value) =>
                  setExpiration(value as ExpirationOption)
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select expiration" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="never">Never</SelectItem>
                  <SelectItem value="30days">30 days</SelectItem>
                  <SelectItem value="90days">90 days</SelectItem>
                  <SelectItem value="1year">1 year</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button onClick={handleCreateKey} disabled={isCreating}>
              {isCreating ? "Creating..." : "Create Key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Show Created Key Dialog */}
      <Dialog
        open={showKeyDialogOpen}
        onOpenChange={(open) => {
          if (!open) {
            setCreatedKey(null);
            setCopied(false);
          }
          setShowKeyDialogOpen(open);
        }}
      >
        <DialogContent showCloseButton={false} className="max-w-[calc(100%-2rem)] sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>API Key Created</DialogTitle>
            <DialogDescription>
              Copy your API key now. You won&apos;t be able to see it again.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4 overflow-hidden">
            <div className="flex items-center gap-2 rounded bg-muted p-3 min-w-0">
              <code className="flex-1 break-all text-xs min-w-0">{createdKey}</code>
              <Button
                variant="ghost"
                size="icon-sm"
                className="shrink-0"
                onClick={() => createdKey && copyToClipboard(createdKey)}
              >
                {copied ? (
                  <RiCheckLine className="h-4 w-4 text-green-500" />
                ) : (
                  <RiFileCopyLine className="h-4 w-4" />
                )}
              </Button>
            </div>
            <div className="flex items-start gap-2 rounded border border-amber-200 bg-amber-50 p-3 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
              <RiAlertLine className="mt-0.5 h-4 w-4 shrink-0" />
              <p className="text-xs">
                Make sure to copy your API key now. For security reasons, it
                cannot be displayed again.
              </p>
            </div>
            <div className="space-y-2 min-w-0">
              <Label>Claude Desktop Configuration</Label>
              <p className="text-xs text-muted-foreground">
                Add this to your Claude Desktop config file:
              </p>
              <div className="relative min-w-0">
                <pre className="max-h-48 overflow-x-auto overflow-y-auto rounded bg-muted p-3 pr-10 text-xs whitespace-pre">
                  {configSnippet}
                </pre>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="absolute right-2 top-2"
                  onClick={() => copyToClipboard(configSnippet)}
                >
                  <RiFileCopyLine className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setShowKeyDialogOpen(false)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete API Key</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{deletingKey?.name}&quot;?
              Any applications using this key will no longer be able to access
              your data.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteKey}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
