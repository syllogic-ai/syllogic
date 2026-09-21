"use client";
import { t as translate } from "@/i18n/translate";

import {
  RiAddLine,
  RiArrowLeftLine,
  RiArrowRightLine,
  RiCloseLine,
  RiLoader4Line,
} from "@remixicon/react";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CategorySelect } from "@/components/categories/category-select";
import { AccountSelect } from "@/components/accounts/account-select";
import { Header } from "@/components/layout/header";
import { ReceiptUploadDropzone } from "@/components/transactions/receipt-upload-dropzone";
import { useReceiptScanController } from "../hooks/use-receipt-scan-controller";
import type { ReceiptGroup } from "../domain/contracts";

function GroupList({ groups }: { groups: ReceiptGroup[] }) {
  if (groups.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        {translate("computingHowThisReceiptWillBeBooked")}
      </p>
    );
  }
  return (
    <ul className="space-y-1">
      {groups.map((group) => (
        <li
          key={`${group.categoryId ?? "uncategorized"}-${group.lineRefs.join(",")}`}
          className="flex items-center justify-between text-xs"
        >
          <span className="truncate pr-2">
            {group.categoryName ?? translate("noCategory")}
          </span>
          <span className="font-medium">{Number(group.amount).toFixed(2)}</span>
        </li>
      ))}
    </ul>
  );
}

export default function ReceiptScanScreen() {
  const {
    accounts,
    categories,
    selectedAccountId,
    setSelectedAccountId,
    step,
    selectedFile,
    previewUrl,
    isUploading,
    isSubmitting,
    pollTimedOut,
    retryPolling,
    selectFile,
    clearFile,
    extract,
    merchantName,
    items,
    itemsTotal,
    detectedTotal,
    canConfirm,
    validationErrors,
    flaggedLineRefs,
    updateItemCategory,
    updateItemAmount,
    updateItemDescription,
    addBlankItem,
    removeItem,
    saveCorrections,
    isSavingCorrections,
    groupPreview,
    isPreviewing,
    confirm,
    goBack,
  } = useReceiptScanController();

  const needsReview = step === "needs_review";

  if (step === "upload") {
    return (
      <>
        <Header title={translate("scanReceipt")} />
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-4 pt-0">
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle>{translate("scanReceipt")}</CardTitle>
              <CardDescription>
                {translate("uploadAPhotoOfYourReceiptToSplitTransactions")}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label>{translate("selectAccount")}</Label>
                {accounts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    {translate("noAccountsFoundPleaseCreateAnAccountFirst")}
                  </p>
                ) : (
                  <AccountSelect
                    accounts={accounts}
                    value={selectedAccountId}
                    onChange={(v) => v && setSelectedAccountId(v)}
                    placeholder={translate("selectAnAccount")}
                    className="w-full"
                    contentClassName="w-auto min-w-[var(--anchor-width)] max-w-[90vw]"
                    itemClassName="pr-10"
                    renderTriggerLabel={(account) => account.name}
                    renderItemLabel={(account) =>
                      `${account.name} (${account.currency})`
                    }
                  />
                )}
              </div>

              <div className="space-y-2">
                <Label>{translate("receiptPhoto")}</Label>
                <ReceiptUploadDropzone
                  onFileSelect={selectFile}
                  onClear={clearFile}
                  previewUrl={previewUrl}
                  selectedFile={selectedFile}
                  isUploading={isUploading}
                />
              </div>
            </CardContent>
            <CardFooter className="justify-between">
              <Button type="button" variant="outline" onClick={goBack}>
                <RiArrowLeftLine className="mr-2 h-4 w-4" />
                {translate("cancel")}
              </Button>
              <Button
                onClick={extract}
                disabled={isUploading || !selectedFile || accounts.length === 0}
              >
                {isUploading ? translate("processing") : translate("continue")}
                <RiArrowRightLine className="ml-2 h-4 w-4" />
              </Button>
            </CardFooter>
          </Card>
        </div>
      </>
    );
  }

  if (step === "extracting") {
    return (
      <>
        <Header title={translate("processingReceipt")} />
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-4 pt-0">
          <Card className="w-full max-w-2xl">
            <CardHeader>
              <CardTitle>{translate("processingReceipt")}</CardTitle>
              <CardDescription>
                {pollTimedOut
                  ? translate("stillWorkingOnItThisIsTakingLongerThanUsual")
                  : translate(
                      "weAreExtractingTheDetailsFromYourReceiptThisCanTakeAMoment",
                    )}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col items-center gap-4 py-8">
              <RiLoader4Line className="h-8 w-8 animate-spin text-muted-foreground" />
            </CardContent>
            <CardFooter className="justify-between">
              <Button type="button" variant="outline" onClick={goBack}>
                <RiArrowLeftLine className="mr-2 h-4 w-4" />
                {translate("back")}
              </Button>
              {pollTimedOut && (
                <Button type="button" onClick={retryPolling}>
                  {translate("checkAgain")}
                </Button>
              )}
            </CardFooter>
          </Card>
        </div>
      </>
    );
  }

  return (
    <>
      <Header
        title={
          needsReview
            ? translate("reviewFlaggedItems")
            : translate("reviewReceiptItems")
        }
      />
      <div className="flex flex-1 flex-col items-center gap-4 p-4 pt-0">
        <Card className="w-full max-w-3xl">
          <CardHeader>
            <CardTitle>
              {needsReview
                ? translate("reviewFlaggedItems")
                : translate("reviewReceiptItems")}
            </CardTitle>
            <CardDescription>
              {needsReview
                ? translate(
                    "someLinesDidNotAddUpFixTheHighlightedLinesBeforeConfirming",
                  )
                : merchantName
                  ? translate("editTheItemsDetectedAtMerchant", {
                      merchant: merchantName,
                    })
                  : translate("editTheDetectedItemsSplitOrAdjustAsNeeded")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              {items.map((item) => {
                const isFlagged =
                  !!item.lineRef && flaggedLineRefs.has(item.lineRef);
                return (
                  <div
                    key={item.key}
                    className={`grid grid-cols-1 gap-2 rounded-lg border p-3 ${
                      needsReview
                        ? "sm:grid-cols-[1fr_100px_auto]"
                        : "sm:grid-cols-[1fr_100px_1fr]"
                    } ${isFlagged ? "border-destructive/50 bg-destructive/10" : ""}`}
                  >
                    {isFlagged && (
                      <span className="text-xs font-medium text-destructive sm:col-span-3">
                        {translate("flagged")}
                      </span>
                    )}
                    {needsReview ? (
                      <div className="flex flex-col justify-center gap-1">
                        <Input
                          value={item.description}
                          onChange={(e) =>
                            updateItemDescription(item.key, e.target.value)
                          }
                          className="h-8 text-sm"
                        />
                        {item.categoryReason && (
                          <span className="text-xs text-muted-foreground">
                            {item.categoryReason}
                          </span>
                        )}
                      </div>
                    ) : (
                      <div className="flex flex-col justify-center">
                        <span className="text-sm">{item.description}</span>
                        {item.categoryReason && (
                          <span className="text-xs text-muted-foreground">
                            {item.categoryReason}
                          </span>
                        )}
                      </div>
                    )}
                    {needsReview ? (
                      <Input
                        type="number"
                        step="0.01"
                        value={item.amount}
                        onChange={(e) =>
                          updateItemAmount(item.key, e.target.value)
                        }
                        className="h-8 text-right text-sm"
                      />
                    ) : (
                      <div className="flex items-center text-sm font-medium sm:justify-end">
                        {Number(item.amount || 0).toFixed(2)}
                      </div>
                    )}
                    {needsReview ? (
                      <div className="flex items-center justify-end">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label={translate("removeLine")}
                          onClick={() => removeItem(item.key)}
                        >
                          <RiCloseLine className="h-4 w-4" />
                        </Button>
                      </div>
                    ) : (
                      <CategorySelect
                        categories={categories}
                        value={item.categoryId ?? ""}
                        onChange={(v) =>
                          updateItemCategory(
                            item.key,
                            v || null,
                            categories.find((c) => c.id === v)?.name ?? null,
                          )
                        }
                        noneLabel={translate("noCategory")}
                        placeholder={translate("selectACategory")}
                        fallbackColor="#666"
                      />
                    )}
                  </div>
                );
              })}
              {needsReview && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addBlankItem}
                >
                  <RiAddLine className="mr-2 h-4 w-4" />
                  {translate("addItem")}
                </Button>
              )}
            </div>

            <div className="rounded-none border p-3 text-xs border-muted bg-muted/40">
              <div className="flex items-center justify-between">
                <span>{translate("itemsTotal")}</span>
                <span className="font-medium">{itemsTotal.toFixed(2)}</span>
              </div>
              {detectedTotal !== null && (
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>{translate("receiptTotalDetected")}</span>
                  <span>{detectedTotal.toFixed(2)}</span>
                </div>
              )}
            </div>

            {!needsReview && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="rounded-none border p-3">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    {translate("perLineCategoryUncollapsed")}
                  </p>
                  {isPreviewing ? (
                    <RiLoader4Line className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    <GroupList groups={groupPreview?.uncollapsed ?? []} />
                  )}
                </div>
                <div className="rounded-none border p-3">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    {translate("whatWillActuallyBeBooked")}
                  </p>
                  {isPreviewing ? (
                    <RiLoader4Line className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    <GroupList groups={groupPreview?.resolved ?? []} />
                  )}
                </div>
              </div>
            )}

            {validationErrors.length > 0 && (
              <ul className="space-y-1 text-xs text-destructive">
                {validationErrors.map((error) => (
                  <li key={error.code + error.lineRefs.join(",")}>
                    {error.message}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
          <CardFooter className="justify-between">
            <Button type="button" variant="outline" onClick={goBack}>
              <RiArrowLeftLine className="mr-2 h-4 w-4" />
              {translate("back")}
            </Button>
            {needsReview ? (
              <Button onClick={saveCorrections} disabled={isSavingCorrections}>
                {isSavingCorrections
                  ? translate("saving")
                  : translate("saveCorrections")}
              </Button>
            ) : (
              <Button onClick={confirm} disabled={isSubmitting || !canConfirm}>
                {isSubmitting
                  ? translate("saving")
                  : translate("createTransactions")}
              </Button>
            )}
          </CardFooter>
        </Card>
      </div>
    </>
  );
}
