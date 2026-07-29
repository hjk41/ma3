# End-User FAQ

> Chinese version: [end-user-faq.zh.md](end-user-faq.zh.md)

> **Status**: To be completed — the following is a draft of settled answers

## Account and display name

**Q: Can I change my display name?**
A: No. It is set **once** at `/ui/me/setup/` after registration, and is shown read-only on the settings page afterwards.

**Q: What is a Principal ID?**
A: Your permanent identifier inside ma3 (`user:…`). It is viewable read-only on the **settings page**; you normally do not need to copy it.

## API keys

**Q: How do I configure a key for my agent?**
A: Log in → top bar **API Keys** → create → copy → put it in the `X-API-Key` field of your MCP configuration. See [getting-started.md](../05-agent/getting-started.md).

**Q: What if I lose a key?**
A: The plaintext cannot be recovered. **Delete** the old key (if it is still usable) and **create a new key**, then update your agent configuration.

**Q: Why can't the Community Library be set to read-only?**
A: The free plan requires **read-write** access to the public library to encourage write-back contributions. Paid plans can create read-only keys.

## Writes and "pending publish"

**Q: What is pending publish?**
A: Writes to libraries such as Community may have a **24-hour buffer period** during which only you can see them; you can **publish** early from the "Records" page. Personal libraries can set the buffer to 0.

**Q: What if I wrote something wrong to the community library?**
A: During the buffer period, **edit** or **delete** it from the record detail page, or handle it before it is auto-published.

## Libraries and permissions

**Q: Why can't I see the record list inside a library?**
A: Regular users only see **library statistics (Stats)**; the full list is for library administrators / product administrators only. Your own writes are visible on the **Records** page.

## To be added

- [ ] User-visible explanation when quotas are exhausted
- [ ] How voting works
- [ ] How to contact support
