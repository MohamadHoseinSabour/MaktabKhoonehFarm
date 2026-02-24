'use client'

import { useEffect, useMemo, useState } from 'react'
import { AdminSidebar } from '@/components/AdminSidebar'
import { Setting, getSettings, saveSettings, validateUploadCookies } from '@/services/api'

type FieldMeta = {
  key: string
  label: string
  description: string
  multiline?: boolean
}

const uploadFields: FieldMeta[] = [
  { key: 'scraper_cookies_json', label: 'کوکی‌های سایت مبدأ (اسکرپر)', description: 'کوکی‌های لاگین سایت مبدأ (مثل مکتب‌خونه) برای اسکرپ و دانلود. فرمت JSON — از افزونه مرورگر Export کنید.', multiline: true },
  { key: 'upload_target_url', label: 'آدرس سایت هدف', description: 'مسیر اصلی وبسایتی که پردازش‌ها به آن ارسال می‌شود.' },
  { key: 'upload_firefox_headless', label: 'حالت مرورگر پنهان', description: 'اجرای مرورگر در پس‌زمینه (بدون رابط گرافیکی). برای فعال‌سازی مقدار "true" تنظیم شود.' },
  { key: 'upload_search_input_selector', label: 'سلکتور فیلد جستجو', description: 'آدرس CSS Selector برای بخش جستجو سایت.' },
  { key: 'upload_course_result_xpath_template', label: 'مسیر عنوان دوره (XPath)', description: 'مسیر XPath برای یافتن دوره‌ها در لیست جستجو.' },
  { key: 'upload_sections_button_xpath', label: 'مسیر لینک فصل‌ها', description: 'مسیر XPath برای دکمه بازکردن صفحات ویدیو یا قسمت‌ها.' },
  { key: 'upload_units_button_xpath', label: 'ورود به ویرایش واحد', description: 'مسیر XPath برای وارد شدن به زمینه ویرایش آموزش.' },
  { key: 'upload_login_check_selector', label: 'بررسی وضعیت ورود', description: 'سلکتوری که پس از لاگین بودن ادمین در صفحه دیده می‌شود.' },
  { key: 'upload_episode_page_indicator_selector', label: 'تایید بارگذاری صفحه قسمت', description: 'سلکتوری که برای اطمینان از لود کامل فرم آپلود بررسی می‌شود.' },
  { key: 'upload_firefox_geckodriver_path', label: 'مسیر درایور', description: 'مسیر مطلق فایل اجرایی Geckodriver برای فایرفاکس.' },
  { key: 'upload_cookies_json', label: 'کوکی‌های نشست (Sessions)', description: 'اطلاعات کوکی‌ها برای حفظ ورود به سیستم (فرمت فقط JSON)', multiline: true },
]

const defaults: Record<string, string> = {
  scraper_cookies_json: '[]',
  upload_target_url: '',
  upload_firefox_headless: 'false',
  upload_search_input_selector: "input[type='search']",
  upload_course_result_xpath_template: "//a[contains(normalize-space(.), {query})]",
  upload_sections_button_xpath: "//a[contains(@href, '/chapters/') and contains(normalize-space(.), 'فصل')]",
  upload_units_button_xpath: "//a[contains(@href, '/units/')]",
  upload_login_check_selector: '',
  upload_episode_page_indicator_selector: '',
  upload_firefox_geckodriver_path: '',
  upload_cookies_json: '[]',
}

function ensureUploadSetting(settings: Setting[], key: string): Setting {
  const found = settings.find((item) => item.key === key)
  if (found) return found
  return {
    id: `virtual-${key}`,
    key,
    value: defaults[key] ?? '',
    category: 'upload_automation',
    description: uploadFields.find((field) => field.key === key)?.description ?? '',
  }
}

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<Setting[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [validating, setValidating] = useState(false)
  const [validateMessage, setValidateMessage] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const load = async () => {
    try {
      const data = await getSettings()
      setSettings(data)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const uploadSettings = useMemo(
    () => uploadFields.map((field) => ensureUploadSetting(settings, field.key)),
    [settings]
  )
  const otherSettings = useMemo(
    () => settings.filter((item) => !uploadFields.some((field) => field.key === item.key)),
    [settings]
  )

  const updateSettingValue = (key: string, value: string) => {
    setSettings((prev) => {
      const idx = prev.findIndex((item) => item.key === key)
      if (idx === -1) {
        return [
          ...prev,
          {
            id: `virtual-${key}`,
            key,
            value,
            category: 'upload_automation',
            description: uploadFields.find((field) => field.key === key)?.description ?? '',
          },
        ]
      }
      const next = [...prev]
      next[idx] = { ...next[idx], value }
      return next
    })
  }

  const persist = async () => {
    setSaving(true)
    setError(null)
    setValidateMessage(null)
    try {
      const uploadDescriptionByKey = new Map(uploadFields.map((field) => [field.key, field.description]))
      const payload = [...otherSettings, ...uploadSettings].map(({ key, value, category, description }) => ({
        key,
        value,
        category: uploadDescriptionByKey.has(key) ? 'upload_automation' : (category ?? null),
        description: uploadDescriptionByKey.get(key) ?? description ?? null,
      }))
      const updated = await saveSettings(payload)
      setSettings(updated)
      setValidateMessage('تنظیمات با موفقیت ذخیره شد.')
    } catch (err) {
      setError((err as Error).message)
      throw err
    } finally {
      setSaving(false)
    }
  }

  const validateCookies = async () => {
    setValidating(true)
    setError(null)
    setValidateMessage(null)
    try {
      await persist()
      const result = await validateUploadCookies()
      setValidateMessage(result.message)
    } catch (err) {
      const message = (err as Error).message
      setError(message)
    } finally {
      setValidating(false)
    }
  }

  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack" style={{ padding: '2.5rem' }}>
        <h1 style={{ marginBottom: '1.5rem' }}>تنظیمات اصلی و اتوماسیون</h1>

        <div className="grid cols-2" style={{ gap: '2rem' }}>
          {uploadFields.map((field) => {
            const item = uploadSettings.find((row) => row.key === field.key)
            if (!item) return null

            if (field.key === 'upload_firefox_headless') {
              const checked = item.value.trim().toLowerCase() === 'true'
              return (
                <div key={field.key} className="stack" style={{ gridColumn: '1 / -1', padding: '1rem', background: 'var(--bg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
                  <label className="row" style={{ justifyContent: 'space-between', gap: '2rem' }}>
                    <div className="stack" style={{ gap: '0.25rem' }}>
                      <strong style={{ fontSize: '1.05rem' }}>{field.label}</strong>
                      <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{field.description}</span>
                    </div>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(event) => updateSettingValue(field.key, event.target.checked ? 'true' : 'false')}
                      style={{ width: '1.5rem', height: '1.5rem' }}
                      dir="ltr"
                    />
                  </label>
                </div>
              )
            }

            return (
              <div key={field.key} className="stack" style={{ gridColumn: field.multiline ? '1 / -1' : 'auto' }}>
                <div className="stack" style={{ gap: '0.25rem', marginBottom: '0.5rem' }}>
                  <strong style={{ fontSize: '0.95rem' }}>{field.label}</strong>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{field.description}</span>
                </div>
                {field.multiline ? (
                  <textarea
                    rows={8}
                    value={item.value}
                    onChange={(event) => updateSettingValue(field.key, event.target.value)}
                    style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                    dir="ltr"
                  />
                ) : (
                  <input
                    value={item.value}
                    onChange={(event) => updateSettingValue(field.key, event.target.value)}
                    dir="ltr"
                  />
                )}
              </div>
            )
          })}
        </div>

        <div className="row" style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border)' }}>
          <button className={`btn ${saving ? 'running' : ''}`} onClick={persist} disabled={saving || validating}>
            {saving ? 'در حال ذخیره...' : 'ذخیره تنظیمات'}
          </button>
          <button className={`btn secondary ${validating ? 'running' : ''}`} onClick={validateCookies} disabled={validating || saving}>
            {validating ? 'در حال بررسی...' : 'بررسی اتصال سرور'}
          </button>

          <button className="btn secondary" onClick={() => setShowAdvanced((prev) => !prev)} style={{ marginRight: 'auto' }}>
            {showAdvanced ? 'مخفی کردن پیشرفته' : 'تنظیمات پیشرفته'}
          </button>
        </div>

        {validateMessage && <div className="status-note" style={{ marginTop: '1rem' }}>{validateMessage}</div>}
        {error && <div className="operation-banner warn" style={{ marginTop: '1rem' }}>{error}</div>}

        {showAdvanced && (
          <div className="stack" style={{ marginTop: '2rem', padding: '1.5rem', background: 'var(--bg)', borderRadius: 'var(--radius-md)' }}>
            <h3 style={{ marginBottom: '1rem' }}>پیکربندی‌های مخفی و سیستم</h3>
            {otherSettings.map((item, index) => (
              <div key={item.id} className="row" style={{ gap: '1rem' }}>
                <strong style={{ flex: '0 0 200px', fontSize: '0.9rem' }} dir="ltr">{item.key}</strong>
                <input
                  style={{ flex: 1 }}
                  value={item.value}
                  onChange={(event) => {
                    const next = [...otherSettings]
                    next[index] = { ...next[index], value: event.target.value }
                    const merged = [...uploadSettings, ...next]
                    setSettings(merged)
                  }}
                  dir="ltr"
                />
              </div>
            ))}
            {otherSettings.length === 0 && <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>هیچ پارامتر اضافه‌ای در پایگاه داده ثبت نشده است.</p>}
          </div>
        )}
      </section>
    </div>
  )
}
