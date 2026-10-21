using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable
#pragma warning disable CA1861 // index composé généré par EF : appelé une fois

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Traces.Migrations
{
    /// <inheritdoc />
    public partial class Span : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "span",
                columns: table => new
                {
                    trace_id = table.Column<string>(type: "char(32)", nullable: false),
                    span_id = table.Column<string>(type: "char(16)", nullable: false),
                    parent_span_id = table.Column<string>(type: "char(16)", nullable: true),
                    trace_state = table.Column<string>(type: "text", nullable: false),
                    name = table.Column<string>(type: "text", nullable: false),
                    kind = table.Column<short>(type: "smallint", nullable: false),
                    start_time_unix_nano = table.Column<long>(type: "bigint", nullable: false),
                    end_time_unix_nano = table.Column<long>(type: "bigint", nullable: false),
                    duree_ms = table.Column<double>(type: "double precision", nullable: false, computedColumnSql: "(end_time_unix_nano - start_time_unix_nano) / 1e6", stored: true),
                    status_code = table.Column<short>(type: "smallint", nullable: false),
                    status_message = table.Column<string>(type: "text", nullable: false),
                    service_name = table.Column<string>(type: "text", nullable: false),
                    resource_attributes = table.Column<string>(type: "jsonb", nullable: false),
                    attributes = table.Column<string>(type: "jsonb", nullable: false),
                    scope_name = table.Column<string>(type: "text", nullable: false),
                    scope_version = table.Column<string>(type: "text", nullable: false),
                    events = table.Column<string>(type: "jsonb", nullable: false),
                    links = table.Column<string>(type: "jsonb", nullable: false),
                    recu_le = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_span", x => new { x.trace_id, x.span_id });
                });

            migrationBuilder.CreateIndex(
                name: "ix_span_attributes",
                table: "span",
                column: "attributes")
                .Annotation("Npgsql:IndexMethod", "gin");

            migrationBuilder.CreateIndex(
                name: "ix_span_parent_span_id",
                table: "span",
                column: "parent_span_id");

            migrationBuilder.CreateIndex(
                name: "ix_span_service_name_start_time_unix_nano",
                table: "span",
                columns: new[] { "service_name", "start_time_unix_nano" });

            // Droits (spec §9.3) : traces_writer n'insère que, traces_reader ne lit que.
            migrationBuilder.Sql("GRANT INSERT ON span TO traces_writer");
            migrationBuilder.Sql("GRANT SELECT ON span TO traces_reader");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "span");
        }
    }
}
