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
  {
    key: 'upload_target_url',
    label: 'Target URL',
    description: 'آدرس صفحه مقصد که باید باز شود.',
  },
  {
    key: 'upload_firefox_headless',
    label: 'Headless Mode',
    description: 'به صورت پیش‌فرض خاموش است (گرافیکی). اگر true شود مرورگر هدلس اجرا می‌شود.',
  },
  {
    key: 'upload_search_input_selector',
    label: 'Search Input Selector',
    description: 'CSS selector برای input جست‌وجوی دوره در سایت مقصد.',
  },
  {
    key: 'upload_course_result_xpath_template',
    label: 'Course Result XPath',
    description: 'XPath نتیجه دوره. از {query} برای نام دوره استفاده کنید.',
  },
  {
    key: 'upload_sections_button_xpath',
    label: 'Sections Button XPath',
    description: 'XPath دکمه فصل‌ها و جلسات.',
  },
  {
    key: 'upload_units_button_xpath',
    label: 'Units Edit XPath',
    description: 'XPath لینک ورود به لیست جلسات (ویرایش جلسات).',
  },
  {
    key: 'upload_login_check_selector',
    label: 'Login Check Selector',
    description: 'CSS selector یک المان که فقط در حالت لاگین دیده می‌شود.',
  },
  {
    key: 'upload_episode_page_indicator_selector',
    label: 'Episode Page Indicator',
    description: 'CSS selector برای تایید باز شدن صفحه اپیزودها (اختیاری).',
  },
  {
    key: 'upload_firefox_geckodriver_path',
    label: 'Geckodriver Path',
    description: 'مسیر geckodriver (اختیاری). اگر خالی باشد مسیر پیش‌فرض سیستم استفاده می‌شود.',
  },
  {
    key: 'upload_cookies_json',
    label: 'Cookies JSON',
    description: 'لیست کوکی‌ها به فرمت JSON (خروجی افزونه یا DevTools).',
    multiline: true,
  },
]

const defaults: Record<string, string> = {
  upload_target_url: '',
  upload_firefox_headless: 'false',
  upload_search_input_selector: "input[type='search']",
  upload_course_result_xpath_template: "//a[contains(normalize-space(.), {query})]",
  upload_sections_button_xpath:
    "//a[contains(@href, '/chapters/') and contains(normalize-space(.), 'فصل') and contains(normalize-space(.), 'جلس')]",
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
      setValidateMessage(message)
    } finally {
      setValidating(false)
    }
  }

  return (
    <div className="admin-layout">
      <AdminSidebar />
      <section className="panel stack">
        <h1>Upload Automation Settings</h1>
        <p dir="rtl">
          حالت پیش‌فرض Firefox گرافیکی است. فقط در صورت نیاز، Headless Mode را روی <code>true</code> بگذارید.
        </p>

        {uploadFields.map((field) => {
          const item = uploadSettings.find((row) => row.key === field.key)
          if (!item) return null

          if (field.key === 'upload_firefox_headless') {
            const checked = item.value.trim().toLowerCase() === 'true'
            return (
              <label key={field.key} className="stack">
                <strong>{field.label}</strong>
                <span>{field.description}</span>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => updateSettingValue(field.key, event.target.checked ? 'true' : 'false')}
                />
              </label>
            )
          }

          return (
            <div key={field.key} className="stack">
              <strong>{field.label}</strong>
              <span>{field.description}</span>
              {field.multiline ? (
                <textarea
                  rows={8}
                  value={item.value}
                  onChange={(event) => updateSettingValue(field.key, event.target.value)}
                />
              ) : (
                <input value={item.value} onChange={(event) => updateSettingValue(field.key, event.target.value)} />
              )}
            </div>
          )
        })}

        <div className="row">
          <button className="btn" onClick={persist} disabled={saving}>
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
          <button className="btn secondary" onClick={validateCookies} disabled={validating || saving}>
            {validating ? 'Validating...' : 'Validate Cookies'}
          </button>
        </div>

        {validateMessage && <p>{validateMessage}</p>}
        {error && <p>{error}</p>}

        <button className="btn secondary" onClick={() => setShowAdvanced((prev) => !prev)}>
          {showAdvanced ? 'Hide Advanced Settings' : 'Show Advanced Settings'}
        </button>

        {showAdvanced &&
          otherSettings.map((item, index) => (
            <div key={item.id} className="stack">
              <strong>{item.key}</strong>
              <input
                value={item.value}
                onChange={(event) => {
                  const next = [...otherSettings]
                  next[index] = { ...next[index], value: event.target.value }
                  const merged = [...uploadSettings, ...next]
                  setSettings(merged)
                }}
              />
            </div>
          ))}
      </section>
    </div>
  )
}
