-- Orders table for the BLMI report store (Supabase SQL editor or any Postgres).
-- The app also creates this table itself on first start; this file is for reference and manual setup.
create table if not exists orders (
  id                    varchar(36) primary key,
  token                 varchar(64)  not null,
  created_at            timestamptz  not null,
  updated_at            timestamptz  not null,
  email                 varchar(320) not null,
  ticker                varchar(32)  not null,
  asset_type            varchar(16)  not null,
  tier                  varchar(16)  not null,
  amount_cents          integer      not null,
  status                varchar(24)  not null,
  stage                 varchar(64),
  stripe_session_id     varchar(255),
  stripe_payment_intent varchar(255),
  analysis_date         varchar(10),
  attempts              integer      not null default 0,
  qc_report             text,
  error                 text,
  pdf_path              varchar(512),
  consent_text          text,
  consent_ip            varchar(64),
  delivered_at          timestamptz
);
create index if not exists ix_orders_status on orders (status);
create index if not exists ix_orders_stripe_session_id on orders (stripe_session_id);
-- Only the server (service role / direct connection) may touch orders; block the public API.
alter table orders enable row level security;
