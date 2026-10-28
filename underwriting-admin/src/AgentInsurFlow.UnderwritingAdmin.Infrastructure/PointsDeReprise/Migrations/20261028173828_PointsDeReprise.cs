using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.PointsDeReprise.Migrations
{
    /// <inheritdoc />
    public partial class PointsDeReprise : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.EnsureSchema(
                name: "points_reprise");

            migrationBuilder.CreateTable(
                name: "checkpoint",
                schema: "points_reprise",
                columns: table => new
                {
                    thread_id = table.Column<string>(type: "text", nullable: false),
                    checkpoint_ns = table.Column<string>(type: "text", nullable: false),
                    checkpoint_id = table.Column<string>(type: "text", nullable: false, collation: "C"),
                    parent_checkpoint_id = table.Column<string>(type: "text", nullable: true, collation: "C"),
                    type = table.Column<string>(type: "text", nullable: false),
                    checkpoint = table.Column<byte[]>(type: "bytea", nullable: false),
                    type_metadata = table.Column<string>(type: "text", nullable: false),
                    metadata = table.Column<byte[]>(type: "bytea", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_checkpoint", x => new { x.thread_id, x.checkpoint_ns, x.checkpoint_id });
                });

            migrationBuilder.CreateTable(
                name: "ecriture",
                schema: "points_reprise",
                columns: table => new
                {
                    thread_id = table.Column<string>(type: "text", nullable: false),
                    checkpoint_ns = table.Column<string>(type: "text", nullable: false),
                    checkpoint_id = table.Column<string>(type: "text", nullable: false, collation: "C"),
                    task_id = table.Column<string>(type: "text", nullable: false, collation: "C"),
                    idx = table.Column<int>(type: "integer", nullable: false),
                    canal = table.Column<string>(type: "text", nullable: false),
                    type = table.Column<string>(type: "text", nullable: false),
                    valeur = table.Column<byte[]>(type: "bytea", nullable: false),
                    task_path = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_ecriture", x => new { x.thread_id, x.checkpoint_ns, x.checkpoint_id, x.task_id, x.idx });
                });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "checkpoint",
                schema: "points_reprise");

            migrationBuilder.DropTable(
                name: "ecriture",
                schema: "points_reprise");
        }
    }
}
