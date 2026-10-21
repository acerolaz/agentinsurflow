using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AgentInsurFlow.UnderwritingAdmin.Infrastructure.Dossiers.Migrations
{
    /// <inheritdoc />
    public partial class Mcd : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "souscripteur",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    nom = table.Column<string>(type: "text", nullable: false),
                    prenom = table.Column<string>(type: "text", nullable: false),
                    date_naissance = table.Column<DateOnly>(type: "date", nullable: false),
                    adresse = table.Column<string>(type: "text", nullable: false),
                    email = table.Column<string>(type: "text", nullable: false),
                    telephone = table.Column<string>(type: "text", nullable: false),
                    situation_familiale = table.Column<string>(type: "text", nullable: false),
                    permis_numero = table.Column<string>(type: "text", nullable: false),
                    permis_date_obtention = table.Column<DateOnly>(type: "date", nullable: false),
                    permis_pays = table.Column<string>(type: "text", nullable: false),
                    code_postal = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_souscripteur", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "conducteur_secondaire",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    souscripteur_id = table.Column<Guid>(type: "uuid", nullable: false),
                    identite = table.Column<string>(type: "text", nullable: false),
                    lien_parente = table.Column<string>(type: "text", nullable: false),
                    historique_permis = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_conducteur_secondaire", x => x.id);
                    table.ForeignKey(
                        name: "fk_conducteur_secondaire_souscripteur_souscripteur_id",
                        column: x => x.souscripteur_id,
                        principalTable: "souscripteur",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "contrat",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    numero_contrat = table.Column<string>(type: "text", nullable: false),
                    souscripteur_id = table.Column<Guid>(type: "uuid", nullable: false),
                    gestionnaire_id = table.Column<string>(type: "text", nullable: false),
                    date_effet = table.Column<DateOnly>(type: "date", nullable: false),
                    statut = table.Column<string>(type: "text", nullable: false),
                    formule = table.Column<string>(type: "text", nullable: false),
                    mis_a_jour = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_contrat", x => x.id);
                    table.ForeignKey(
                        name: "fk_contrat_souscripteur_souscripteur_id",
                        column: x => x.souscripteur_id,
                        principalTable: "souscripteur",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "decision",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    contrat_id = table.Column<Guid>(type: "uuid", nullable: false),
                    decision_rendue = table.Column<string>(type: "text", nullable: false),
                    contrat_type = table.Column<string>(type: "text", nullable: false),
                    score = table.Column<decimal>(type: "numeric", nullable: false),
                    version_bareme = table.Column<string>(type: "text", nullable: false),
                    regle_id = table.Column<string>(type: "text", nullable: false),
                    motifs = table.Column<string>(type: "jsonb", nullable: false),
                    citations = table.Column<string>(type: "jsonb", nullable: false),
                    etat_validation = table.Column<string>(type: "text", nullable: false),
                    auteur = table.Column<string>(type: "text", nullable: false),
                    horodatage = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_decision", x => x.id);
                    table.ForeignKey(
                        name: "fk_decision_contrat_contrat_id",
                        column: x => x.contrat_id,
                        principalTable: "contrat",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "garantie",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    contrat_id = table.Column<Guid>(type: "uuid", nullable: false),
                    type = table.Column<string>(type: "text", nullable: false),
                    formule = table.Column<string>(type: "text", nullable: false),
                    plafond_indemnisation = table.Column<decimal>(type: "numeric", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_garantie", x => x.id);
                    table.ForeignKey(
                        name: "fk_garantie_contrat_contrat_id",
                        column: x => x.contrat_id,
                        principalTable: "contrat",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "piece_justificative",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    contrat_id = table.Column<Guid>(type: "uuid", nullable: false),
                    type = table.Column<string>(type: "text", nullable: false),
                    nom_fichier = table.Column<string>(type: "text", nullable: false),
                    url_blob = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_piece_justificative", x => x.id);
                    table.ForeignKey(
                        name: "fk_piece_justificative_contrat_contrat_id",
                        column: x => x.contrat_id,
                        principalTable: "contrat",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "prime",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    contrat_id = table.Column<Guid>(type: "uuid", nullable: false),
                    prime_pure = table.Column<decimal>(type: "numeric", nullable: false),
                    taxe_fiscale = table.Column<decimal>(type: "numeric", nullable: false),
                    contribution_fgao = table.Column<decimal>(type: "numeric", nullable: false),
                    taxe_attentats_fgti = table.Column<decimal>(type: "numeric", nullable: false),
                    frais_dossier = table.Column<decimal>(type: "numeric", nullable: false),
                    remises = table.Column<decimal>(type: "numeric", nullable: false),
                    surprimes = table.Column<decimal>(type: "numeric", nullable: false),
                    prime_ht = table.Column<decimal>(type: "numeric(12,2)", precision: 12, scale: 2, nullable: false),
                    prime_ttc = table.Column<decimal>(type: "numeric(12,2)", precision: 12, scale: 2, nullable: false),
                    periodicite = table.Column<string>(type: "text", nullable: false),
                    date_effet = table.Column<DateOnly>(type: "date", nullable: false),
                    etat_validation = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_prime", x => x.id);
                    table.ForeignKey(
                        name: "fk_prime_contrat_contrat_id",
                        column: x => x.contrat_id,
                        principalTable: "contrat",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "releve_information",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    contrat_id = table.Column<Guid>(type: "uuid", nullable: false),
                    crm_bonus_malus = table.Column<decimal>(type: "numeric", nullable: false),
                    nb_suspensions_permis = table.Column<int>(type: "integer", nullable: false),
                    nb_resiliations = table.Column<int>(type: "integer", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_releve_information", x => x.id);
                    table.ForeignKey(
                        name: "fk_releve_information_contrat_contrat_id",
                        column: x => x.contrat_id,
                        principalTable: "contrat",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "signalement_fraude",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    contrat_id = table.Column<Guid>(type: "uuid", nullable: false),
                    motif = table.Column<string>(type: "text", nullable: false),
                    signale_le = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    statut = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_signalement_fraude", x => x.id);
                    table.ForeignKey(
                        name: "fk_signalement_fraude_contrat_contrat_id",
                        column: x => x.contrat_id,
                        principalTable: "contrat",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "vehicule",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    contrat_id = table.Column<Guid>(type: "uuid", nullable: false),
                    immatriculation = table.Column<string>(type: "text", nullable: false),
                    vin = table.Column<string>(type: "text", nullable: false),
                    marque = table.Column<string>(type: "text", nullable: false),
                    modele = table.Column<string>(type: "text", nullable: false),
                    version = table.Column<string>(type: "text", nullable: false),
                    puissance_fiscale_cv = table.Column<int>(type: "integer", nullable: false),
                    puissance_din = table.Column<int>(type: "integer", nullable: false),
                    carburant = table.Column<string>(type: "text", nullable: false),
                    date1re_mise_circulation = table.Column<DateOnly>(type: "date", nullable: false),
                    type_usage = table.Column<string>(type: "text", nullable: false),
                    km_annuel_estime = table.Column<int>(type: "integer", nullable: false),
                    mode_stationnement = table.Column<string>(type: "text", nullable: false),
                    code_postal_stationnement = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_vehicule", x => x.id);
                    table.ForeignKey(
                        name: "fk_vehicule_contrat_contrat_id",
                        column: x => x.contrat_id,
                        principalTable: "contrat",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "franchise",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    garantie_id = table.Column<Guid>(type: "uuid", nullable: false),
                    garantie_liee = table.Column<string>(type: "text", nullable: false),
                    montant = table.Column<decimal>(type: "numeric", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_franchise", x => x.id);
                    table.ForeignKey(
                        name: "fk_franchise_garantie_garantie_id",
                        column: x => x.garantie_id,
                        principalTable: "garantie",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "sinistre",
                columns: table => new
                {
                    id = table.Column<Guid>(type: "uuid", nullable: false),
                    releve_information_id = table.Column<Guid>(type: "uuid", nullable: false),
                    date_sinistre = table.Column<DateOnly>(type: "date", nullable: false),
                    nature = table.Column<string>(type: "text", nullable: false),
                    taux_responsabilite = table.Column<decimal>(type: "numeric", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("pk_sinistre", x => x.id);
                    table.ForeignKey(
                        name: "fk_sinistre_releve_information_releve_information_id",
                        column: x => x.releve_information_id,
                        principalTable: "releve_information",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "ix_conducteur_secondaire_souscripteur_id",
                table: "conducteur_secondaire",
                column: "souscripteur_id");

            migrationBuilder.CreateIndex(
                name: "ix_contrat_gestionnaire_id",
                table: "contrat",
                column: "gestionnaire_id");

            migrationBuilder.CreateIndex(
                name: "ix_contrat_numero_contrat",
                table: "contrat",
                column: "numero_contrat",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "ix_contrat_souscripteur_id",
                table: "contrat",
                column: "souscripteur_id",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "ix_decision_contrat_id",
                table: "decision",
                column: "contrat_id");

            migrationBuilder.CreateIndex(
                name: "ix_franchise_garantie_id",
                table: "franchise",
                column: "garantie_id",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "ix_garantie_contrat_id",
                table: "garantie",
                column: "contrat_id");

            migrationBuilder.CreateIndex(
                name: "ix_piece_justificative_contrat_id",
                table: "piece_justificative",
                column: "contrat_id");

            migrationBuilder.CreateIndex(
                name: "ix_prime_contrat_id",
                table: "prime",
                column: "contrat_id",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "ix_releve_information_contrat_id",
                table: "releve_information",
                column: "contrat_id",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "ix_signalement_fraude_contrat_id",
                table: "signalement_fraude",
                column: "contrat_id");

            migrationBuilder.CreateIndex(
                name: "ix_sinistre_releve_information_id",
                table: "sinistre",
                column: "releve_information_id");

            migrationBuilder.CreateIndex(
                name: "ix_vehicule_contrat_id",
                table: "vehicule",
                column: "contrat_id",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "conducteur_secondaire");

            migrationBuilder.DropTable(
                name: "decision");

            migrationBuilder.DropTable(
                name: "franchise");

            migrationBuilder.DropTable(
                name: "piece_justificative");

            migrationBuilder.DropTable(
                name: "prime");

            migrationBuilder.DropTable(
                name: "signalement_fraude");

            migrationBuilder.DropTable(
                name: "sinistre");

            migrationBuilder.DropTable(
                name: "vehicule");

            migrationBuilder.DropTable(
                name: "garantie");

            migrationBuilder.DropTable(
                name: "releve_information");

            migrationBuilder.DropTable(
                name: "contrat");

            migrationBuilder.DropTable(
                name: "souscripteur");
        }
    }
}
