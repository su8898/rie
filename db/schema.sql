-- Canonical RIE schema (PostgreSQL 16). Generated from server/models.py.
-- Dev uses SQLite via create_all(); this file is the reviewed production DDL.

CREATE TABLE accidents (
	accident_id VARCHAR NOT NULL, 
	case_number VARCHAR, 
	"when" DATE NOT NULL, 
	"where" VARCHAR NOT NULL, 
	vehicles JSON NOT NULL, 
	parties JSON NOT NULL, 
	oar_occupants INTEGER, 
	sources JSON NOT NULL, 
	claims JSON NOT NULL, 
	PRIMARY KEY (accident_id)
);

CREATE TABLE app_users (
	id SERIAL NOT NULL, 
	username VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	role VARCHAR NOT NULL, 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE claims (
	claim_id VARCHAR NOT NULL, 
	claim_type VARCHAR NOT NULL, 
	party_token VARCHAR NOT NULL, 
	accident_date DATE NOT NULL, 
	lodged_on DATE NOT NULL, 
	raw JSON NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (claim_id)
);

CREATE TABLE ref_cap (
	effective_from DATE NOT NULL, 
	annual_cap FLOAT NOT NULL, 
	PRIMARY KEY (effective_from)
);

CREATE TABLE ref_empirical (
	kind VARCHAR NOT NULL, 
	code VARCHAR NOT NULL, 
	median FLOAT NOT NULL, 
	PRIMARY KEY (kind, code)
);

CREATE TABLE ref_nappi_sep (
	nappi_code VARCHAR NOT NULL, 
	sep FLOAT NOT NULL, 
	PRIMARY KEY (nappi_code)
);

CREATE TABLE ref_negotiated (
	kind VARCHAR NOT NULL, 
	code VARCHAR NOT NULL, 
	rate FLOAT NOT NULL, 
	PRIMARY KEY (kind, code)
);

CREATE TABLE ref_non_bench (
	code VARCHAR NOT NULL, 
	PRIMARY KEY (code)
);

CREATE TABLE ref_preauth (
	code VARCHAR NOT NULL, 
	PRIMARY KEY (code)
);

CREATE TABLE ref_raf2022 (
	code VARCHAR NOT NULL, 
	rate FLOAT NOT NULL, 
	PRIMARY KEY (code)
);

CREATE TABLE ref_rpl (
	code VARCHAR NOT NULL, 
	gp FLOAT NOT NULL, 
	spec FLOAT, 
	PRIMARY KEY (code)
);

CREATE TABLE transition_log (
	id SERIAL NOT NULL, 
	entity_type VARCHAR NOT NULL, 
	entity_id VARCHAR NOT NULL, 
	from_state VARCHAR NOT NULL, 
	to_state VARCHAR NOT NULL, 
	action VARCHAR NOT NULL, 
	actor VARCHAR NOT NULL, 
	role VARCHAR NOT NULL, 
	at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	detail JSON NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE billing_lines (
	id SERIAL NOT NULL, 
	claim_id VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	code VARCHAR NOT NULL, 
	billed FLOAT NOT NULL, 
	reference FLOAT, 
	payable FLOAT NOT NULL, 
	src VARCHAR NOT NULL, 
	legal_status VARCHAR, 
	needs_review BOOLEAN NOT NULL, 
	reasons JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (claim_id)
);

CREATE TABLE claim_lifecycle (
	claim_id VARCHAR NOT NULL, 
	stage VARCHAR NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (claim_id), 
	FOREIGN KEY(claim_id) REFERENCES claims (claim_id)
);

CREATE TABLE determinations (
	id SERIAL NOT NULL, 
	claim_id VARCHAR NOT NULL, 
	accident_id VARCHAR NOT NULL, 
	accident_action VARCHAR NOT NULL, 
	band VARCHAR NOT NULL, 
	score INTEGER NOT NULL, 
	disposition VARCHAR NOT NULL, 
	validated BOOLEAN NOT NULL, 
	convergence FLOAT NOT NULL, 
	medical_payable FLOAT NOT NULL, 
	net_payable FLOAT NOT NULL, 
	eligible_to_pay BOOLEAN NOT NULL, 
	reasons JSON NOT NULL, 
	shadow_signals JSON NOT NULL, 
	holds JSON NOT NULL, 
	engine_version VARCHAR NOT NULL, 
	ruleset_effective VARCHAR NOT NULL, 
	reference_edition VARCHAR NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (claim_id)
);

CREATE TABLE litigation (
	id SERIAL NOT NULL, 
	claim_id VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	default_judgment BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (claim_id)
);

CREATE TABLE merits_determination (
	claim_id VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	fault_pct FLOAT, 
	ground VARCHAR, 
	PRIMARY KEY (claim_id), 
	FOREIGN KEY(claim_id) REFERENCES claims (claim_id)
);

CREATE TABLE offers (
	id SERIAL NOT NULL, 
	claim_id VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	total FLOAT NOT NULL, 
	gated_by JSON NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (claim_id)
);

CREATE TABLE serious_injury (
	id SERIAL NOT NULL, 
	claim_id VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	list_match BOOLEAN NOT NULL, 
	wpi FLOAT, 
	narrative BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (claim_id)
);

CREATE TABLE undertakings (
	id SERIAL NOT NULL, 
	claim_id VARCHAR NOT NULL, 
	origin VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	scope_dx JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (claim_id)
);

CREATE TABLE offer_heads (
	id SERIAL NOT NULL, 
	offer_id INTEGER NOT NULL, 
	head VARCHAR NOT NULL, 
	amount FLOAT NOT NULL, 
	detail JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(offer_id) REFERENCES offers (id)
);

CREATE TABLE undertaking_invoices (
	id SERIAL NOT NULL, 
	undertaking_id INTEGER NOT NULL, 
	status VARCHAR NOT NULL, 
	billed FLOAT NOT NULL, 
	payable FLOAT NOT NULL, 
	reasons JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(undertaking_id) REFERENCES undertakings (id)
);
